FROM nvdl.githost.io:4678/dgx/mxnet:17.03-devel

# install R support
RUN apt-get update 
# RUN apt-get -y upgrade
# RUN apt-get -y install r-base r-base-dev sudo

#RUN HOME=/opt bash /opt/mxnet/setup-utils/install-mxnet-ubuntu-r.sh

# install Jupyter notebook
RUN pip install jupyter

COPY jupyter_notebook_config.py /root/.jupyter/jupyter_notebook_config.py
RUN cd /workspace

# expose port for Jupyter notebook
EXPOSE 8888
