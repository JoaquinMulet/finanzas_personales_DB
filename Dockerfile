# Stage 1: "builder" - Instala las dependencias en un entorno virtual
FROM python:3.11-bullseye as builder

# Crea un entorno de trabajo y un entorno virtual
WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copia e instala los requerimientos
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: "final" - Construye la imagen de producción ligera
FROM python:3.11-slim-bullseye

WORKDIR /app

# Copia el entorno virtual con las dependencias desde la etapa "builder"
COPY --from=builder /opt/venv /opt/venv

# Copia el código de tu aplicación
COPY . .

# Activa el entorno virtual para los comandos que se ejecuten
ENV PATH="/opt/venv/bin:$PATH"

# Comando que Railway ejecutará al iniciar el contenedor.
# Se conectará a la base de datos usando la variable de entorno DATABASE_URL
# y creará el esquema de la base de datos.
CMD ["python", "database_builder.py"]
