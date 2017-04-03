#!/bin/bash
nvidia-docker run --rm -it -v `pwd`:/mxnet_experiments -p 8888:8888 mxnet_attention
