FROM python:3.11.2
WORKDIR /home/bot
COPY ./ .
RUN pip install -r /home/bot/requirements.txt
#RUN python3 ./frlbot.py -d -n
CMD ["python3", "./main.py"]
