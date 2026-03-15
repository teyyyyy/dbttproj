# Café Discovery Platform

A web application for connecting home-based café vendors with customers.

## Features

- User registration and authentication (customers, vendors, admins)
- Café management for vendors
- Menu item management
- Order placement and management
- Loyalty points system
- Reviews and ratings
- Admin dashboard for platform metrics

## Tech Stack

- FastAPI
- SQLAlchemy
- Jinja2 templates
- SQLite (default, configurable)

## Setup

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Run the application:
   ```
   uvicorn main:app --reload
   ```

3. Access at http://localhost:8000

## API Documentation

Available at http://localhost:8000/docs

## Directory Structure

- `app/`: Main application code
  - `models/`: Database models
  - `routes/`: API routes
  - `schemas/`: Pydantic schemas
  - `utils/`: Utilities (auth, database)
  - `templates/`: HTML templates
  - `static/`: Static files (CSS, JS)
- `tests/`: Unit tests
- `main.py`: Application entry point
- `requirements.txt`: Dependencies# dbttproj
