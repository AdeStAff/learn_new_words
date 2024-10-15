# Step 1: Use official Python image
FROM python:3.12.6-slim

# Step 2: Set working directory
WORKDIR /app

# Step 3: Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Step 4: Copy application code (but excluding files from .dockerignore)
COPY . .

# Step 5: Expose port 8000
EXPOSE 8000

# Step 6: Command to run the application
CMD ["python", "run.py"]