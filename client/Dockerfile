# Cliente — Ubuntu 22.04
#
# Consumidor de las API REST de los dos servidores. Guarda un historial
# local de comunicaciones en SQLite (volumen client_history).
FROM ubuntu:22.04

RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-pip \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python3", "client.py"]
