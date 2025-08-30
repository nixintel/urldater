# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies and Google Chrome
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    golang \
    git \
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y \
        google-chrome-stable \
        xvfb \
        unzip \
        curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install OpenRDAP
RUN go install github.com/openrdap/rdap/cmd/rdap@latest \
    && mv /root/go/bin/rdap /usr/local/bin/ \
    && chmod +x /usr/local/bin/rdap

# Install ChromeDriver
RUN CHROME_VERSION=$(google-chrome-stable --version | awk '{print $3}') \
    && wget -q https://storage.googleapis.com/chrome-for-testing-public/$CHROME_VERSION/linux64/chromedriver-linux64.zip -O /tmp/chromedriver.zip \
    && unzip /tmp/chromedriver.zip -d /tmp/ \
    && mv /tmp/chromedriver-linux64/chromedriver /usr/bin/chromedriver \
    && chmod +x /usr/bin/chromedriver \
    && rm -rf /tmp/chromedriver* \
    && ln -sf /usr/bin/chromedriver /usr/local/bin/chromedriver

# Create and set the working directory
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install Python dependencies
ENV PIP_ROOT_USER_ACTION=ignore
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose the port the app runs on
EXPOSE 5000

# Command to run the application using gunicorn with optimized settings for Selenium
CMD ["gunicorn", "--bind", "0.0.0.0:5000", \
     "--workers", "3", \
     "--timeout", "120", \
     "--graceful-timeout", "60", \
     "--max-requests", "1000", \
     "--max-requests-jitter", "50", \
     "--worker-class", "sync", \
     "--preload", \
     "--worker-tmp-dir", "/dev/shm", \
     "app:app"]