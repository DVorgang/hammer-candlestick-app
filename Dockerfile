FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (curl for healthchecks, build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Set default timezone to US Eastern (market time)
ENV TZ=America/New_York
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Copy Python requirements & install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application codebase
COPY . .

# Expose Streamlit UI port
EXPOSE 8501

# Default command launches Streamlit UI
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
