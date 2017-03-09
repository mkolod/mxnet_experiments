FROM nvdl.githost.io:4678/dgx/mxnet:17.04-devel

# install R support
RUN apt-get update && apt-get -y upgrade
RUN apt-get -y install r-base r-base-dev sudo

#RUN HOME=/opt bash /opt/mxnet/setup-utils/install-mxnet-ubuntu-r.sh

# install Jupyter notebook
RUN pip install jupyter

# install Scala support
RUN cd /opt/mxnet
RUN apt-get -y install maven openjdk-8-jdk scala
RUN cd /opt/mxnet && make scalapkg && make scalainstall
#RUN make scalainstall

# Python3 support
RUN apt-get -y install python3-pip

COPY jupyter_notebook_config.py /root/.jupyter/jupyter_notebook_config.py
#RUN cd /workspace

# expose port for Jupyter notebook
EXPOSE 8888
