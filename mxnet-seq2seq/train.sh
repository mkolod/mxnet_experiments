#!/bin/bash
python cudnn_lstm_bucketing.py --num-layers 1 --num-hidden 128 --num-embed 128 --gpus 0 --num-epochs 1 --optimizer adam --batch-size 1

