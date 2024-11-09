# Step 1: Use official Python image
FROM python:3.12.6-slim

# Step 2: Set working directory
WORKDIR /app

# Step 3: Install ffmpeg
RUN apt-get update && apt-get install -y ffmpeg

# Step 4: Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Step 5: Copy application code (but excluding files from .dockerignore)
COPY . .

# Step 6: Expose port 8000
EXPOSE 8000

# Step 7: Command to run the application
CMD ["python", "run.py"]