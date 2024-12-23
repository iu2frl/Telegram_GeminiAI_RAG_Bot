FROM python:3.11.2
WORKDIR /home/bot
COPY ./ .
RUN pip install -r /home/bot/requirements.txt
RUN  echo BUILD_DATE=$(date +%Y%m%d-%H%M%S) > .env
CMD ["python3", "./main.py"]
