import logging
import random
import numpy as np
import mxnet as mx
from tqdm import tqdm
from lstm import enc_lstm_unroll, dec_lstm_unroll
from datautils import Seq2SeqIter, default_build_vocab
from datautils import SimpleBatch, Perplexity, default_text2id


class Seq2Seq(object):
    def __init__( self, seq_len, batch_size, num_layers,
                  input_size, embed_size, hidden_size,
                  output_size, dropout, mx_ctx=mx.cpu() ):
        self.embed_dict = {}
        self.eval_embed_dict = {}
        self.seq_len = seq_len
        self.batch_size = batch_size
        self.num_layers = num_layers
        self.input_size = input_size
        self.embed_size = embed_size
        self.hidden_size = hidden_size
        self.dropout = dropout
        self.output_size = output_size
        self.ctx = mx_ctx
        # for training
        self.embed = self.build_embed_dict(self.seq_len + 1)
        self.encoder = self.build_lstm_encoder()
        self.decoder = self.build_lstm_decoder()
        self.init_h = mx.nd.zeros((self.batch_size, self.hidden_size), self.ctx)
        self.init_c = mx.nd.zeros((self.batch_size, self.hidden_size), self.ctx)
        # for evaluation
        self.eval_embed = self.build_embed_dict(self.seq_len+1, is_train=False)
        self.eval_encoder = self.build_lstm_encoder(is_train=False)
        self.eval_decoder = self.build_lstm_decoder(is_train=False)

    def gen_embed_sym( self ):
        data = mx.sym.Variable('data')
        embed_weight = mx.sym.Variable("embed_weight")
        embed_sym = mx.sym.Embedding(data=data, input_dim=self.input_size,
                                     weight=embed_weight,
                                     output_dim=self.embed_size, name='embed')
        return embed_sym

    def build_embed_layer( self, default_bucket, is_train=True, bef_args=None ):

        embed_sym = self.gen_embed_sym()
        if is_train:
            embed = mx.mod.Module(symbol=embed_sym, data_names=('data',), label_names=None, context=self.ctx)

            embed.bind(data_shapes=[('data', (self.batch_size, default_bucket)), ], for_training=is_train)

            embed.init_params(initializer=mx.init.Xavier(factor_type="in", magnitude=2.34), arg_params=bef_args)
            embed.init_optimizer(
                optimizer='adam',
                optimizer_params={
                    'learning_rate': 0.02,
                    'wd': 0.,
                    'beta1': 0.5,
                })
        else:
            batch = 1
            embed = mx.mod.Module(symbol=embed_sym, data_names=('data',), label_names=None, context=self.ctx)
            embed.bind(data_shapes=[('data', (batch, default_bucket)), ], for_training=is_train)
            embed.init_params(initializer=mx.init.Xavier(factor_type="in", magnitude=2.34), arg_params=bef_args)
        return embed

    def build_embed_dict( self, default_bucket, is_train=True ):
        sym = self.gen_embed_sym()
        batch = self.batch_size if is_train else 1
        if len(self.embed_dict.keys()) > 1:
            default_embed = self.embed_dict[0]
            module = mx.mod.Module(symbol=sym, data_names=('data',), label_names=None, context=self.ctx)
            module.bind(data_shapes=[('data', (batch, default_bucket))], label_shapes=None,
                        for_training=is_train, force_rebind=False,
                        shared_module=default_embed)
        else:
            default_embed = self.build_embed_layer(default_bucket, is_train=is_train)

        self.embed_dict[default_bucket] = default_embed

        for i in range(1, self.seq_len + 1):
            module = mx.mod.Module(symbol=sym, data_names=('data',), label_names=None, context=self.ctx)
            module.bind(data_shapes=[('data', (batch, i))], label_shapes=None,
                        for_training=default_embed.for_training,
                        inputs_need_grad=default_embed.inputs_need_grad,
                        force_rebind=False, shared_module=default_embed)
            module.borrow_optimizer(default_embed)
            self.embed_dict[i] = module
        return self.embed_dict

    def build_lstm_encoder( self, is_train=True, bef_args=None ):
        enc_lstm_sym = enc_lstm_unroll(num_lstm_layer=self.num_layers,
                                       seq_len=self.seq_len, num_hidden=self.hidden_size)
        if is_train:
            encoder = mx.mod.Module(symbol=enc_lstm_sym, data_names=('data', 'l0_init_c', 'l0_init_h'),
                                    label_names=None, context=self.ctx)

            encoder.bind(data_shapes=[('data', (self.batch_size, self.seq_len, self.embed_size)),
                                      ('l0_init_c', (self.batch_size, self.hidden_size)),
                                      ('l0_init_h', (self.batch_size, self.hidden_size))],
                         inputs_need_grad=True,
                         for_training=is_train)

            encoder.init_params(initializer=mx.init.Xavier(factor_type="in", magnitude=2.34), arg_params=bef_args)
            encoder.init_optimizer(
                optimizer='adam',
                optimizer_params={
                    'learning_rate': 0.02,
                    'wd': 0.,
                    'beta1': 0.5,
                })
        else:
            batch = 1
            encoder = mx.mod.Module(symbol=enc_lstm_sym, data_names=('data', 'l0_init_c', 'l0_init_h'),
                                    label_names=None, context=self.ctx)

            encoder.bind(data_shapes=[('data', (batch, self.seq_len, self.embed_size)),
                                      ('l0_init_c', (batch, self.hidden_size)),
                                      ('l0_init_h', (batch, self.hidden_size))],
                         for_training=is_train)

            encoder.init_params(initializer=mx.init.Xavier(factor_type="in", magnitude=2.34), arg_params=bef_args)

        return encoder

    def build_lstm_decoder( self, is_train=True, bef_args=None ):
        def gen_dec_sym( seq_len ):
            sym = dec_lstm_unroll(1, seq_len, self.hidden_size, self.input_size, 0., is_train=is_train)
            data_names = ['data'] + ['l0_init_c', 'l0_init_h']
            label_names = ['softmax_label']
            return (sym, data_names, label_names)

        if is_train:
            decoder = mx.mod.BucketingModule(gen_dec_sym, default_bucket_key=self.seq_len + 1, context=self.ctx)
            decoder.bind(data_shapes=[('data', (self.batch_size, self.seq_len + 1, self.embed_size)),
                                      ('l0_init_c', (self.batch_size, self.hidden_size)),
                                      ('l0_init_h', (self.batch_size, self.hidden_size))],
                         label_shapes=[('softmax_label', (self.batch_size, self.seq_len + 1))],
                         inputs_need_grad=True,
                         for_training=is_train, )

            decoder.init_params(initializer=mx.init.Xavier(factor_type="in", magnitude=2.34), arg_params=bef_args)
            decoder.init_optimizer(
                optimizer='adam',
                optimizer_params={
                    'learning_rate': 0.02,
                    'wd': 0.,
                    'beta1': 0.5,
                })
        else:
            batch = 1
            decoder = mx.mod.BucketingModule(gen_dec_sym, default_bucket_key=self.seq_len + 1, context=self.ctx)

            decoder.bind(data_shapes=[('data', (batch, self.seq_len + 1, self.embed_size)),
                                      ('l0_init_c', (batch, self.hidden_size)),
                                      ('l0_init_h', (batch, self.hidden_size))],
                         label_shapes=[('softmax_label', (1, self.seq_len + 1))],
                         inputs_need_grad=False,
                         for_training=False)

            decoder.init_params(initializer=mx.init.Xavier(factor_type="in", magnitude=2.34), arg_params=bef_args)

        return decoder

    def train_batch( self, enc_input_batch, dec_input_batch, dec_target_batch, is_train=True ):

        self.embed[self.seq_len].forward(mx.io.DataBatch([enc_input_batch], []))
        enc_word_vecs = self.embed[self.seq_len].get_outputs()[0]

        self.encoder.forward(mx.io.DataBatch([enc_word_vecs, self.init_c, self.init_h], []))
        enc_last_h = self.encoder.get_outputs()[0]

        dec_seq_len = dec_input_batch.shape[1]

        self.embed[dec_seq_len].forward(mx.io.DataBatch([dec_input_batch], []))
        dec_word_vecs = self.embed[dec_seq_len].get_outputs()[0]

        self.decoder.forward(SimpleBatch(data_names=['data', 'l0_init_c', 'l0_init_h'],
                                         data=[dec_word_vecs, self.init_c, enc_last_h],
                                         label_names=['softmax_label'],
                                         label=[dec_target_batch],
                                         bucket_key=dec_seq_len))
        output = self.decoder.get_outputs()[0]
        print(output)
        ppl = Perplexity(dec_target_batch.asnumpy(), output.asnumpy())
        self.decoder.backward()
        dec_word_vecs_grad = self.decoder.get_input_grads()[0]
        grad_last_h = self.decoder.get_input_grads()[2]
        self.decoder.update()
        self.embed_dict[dec_seq_len].backward([dec_word_vecs_grad])
        self.embed_dict[dec_seq_len].update()
        self.encoder.backward([grad_last_h])
        enc_word_vecs_grad = self.encoder.get_input_grads()[0]
        self.encoder.update()
        self.embed_dict[self.seq_len].backward([enc_word_vecs_grad])
        self.embed_dict[self.seq_len].update()
        return ppl

    def train( self, dataset, epoch ):
        for i in range(epoch):
            print("number of epochs: %d" % epoch)
            ppl = 0
            count = 0
            for batch in tqdm(dataset):
                count += 1
                enc_in = mx.nd.array(batch['enc_batch_in'], self.ctx)
                dec_in = mx.nd.array(batch['dec_batch_in'], self.ctx)
                dec_tr = mx.nd.array(batch['dec_batch_tr'], self.ctx)
                cur_ppl = self.train_batch(enc_input_batch=enc_in,
                                           dec_input_batch=dec_in,
                                           dec_target_batch=dec_tr)
                ppl = ppl + cur_ppl

                print 'epoch %d, ppl is %f' % (i, cur_ppl)
                if count > 100:
                   return 

    # TODO
    def eval( self, sentence, vocab_rsd, vocab ):
        ids = default_text2id(sentence, vocab_rsd, 15, vocab)
        print ids
