# Container del bridge radar StormShift su Cloudflare.
# Stesso server del PC (stormshift_meteohub_server.py): qui le credenziali ARCO
# arrivano come variabili d'ambiente dal Worker, non dal vault di Windows.
FROM python:3.12-slim

WORKDIR /app
COPY stormshift-requirements.txt .
RUN pip install --no-cache-dir -r stormshift-requirements.txt
COPY stormshift_meteohub_server.py .

EXPOSE 8000
CMD ["uvicorn", "stormshift_meteohub_server:app", "--host", "0.0.0.0", "--port", "8000"]
