FROM python:3.10-slim

WORKDIR /app

# Instalar las dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código del proyecto
COPY . .

# Ejecutar de forma no bufferizada (para ver los logs en vivo)
CMD ["python", "-u", "linkedin_search.py"]
