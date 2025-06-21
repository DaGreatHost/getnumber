FROM python:3.11-slim

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the bot code
COPY . .

# Create directory for database
RUN mkdir -p /app/data

# Run the bot
CMD ["python", "bot.py"]
