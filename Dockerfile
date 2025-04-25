# Use a lightweight Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies incl. MySQL client
RUN apt-get update && \
    apt-get install -y default-mysql-client gcc libmariadb-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy app files
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Set timezone
ENV TZ=UTC

# Start script
CMD ["python", "main.py"]