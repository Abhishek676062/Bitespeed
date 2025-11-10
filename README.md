Bitespeed Backend Task: Identity Reconciliation
This is a Python FastAPI application that solves the Bitespeed Identity Reconciliation backend assessment. The service exposes a single /identify endpoint that receives contact information (email, phone number) and consolidates identities based on matching data.

🚀 Tech Stack
Python 3.11

FastAPI: For the web server and API endpoints.

Uvicorn: As the ASGI server (run by Gunicorn in production).

Gunicorn: As the production-ready web server.

SQLAlchemy: For the ORM (Object Relational Mapper).

SQLite: As the database for local and test deployment.

💻 Local Setup & Installation
Follow these steps to get the project running on your local machine.

Clone the repository:

Bash

git clone https://github.com/Abhishek676062/Bitespeed.git
cd your-repo-name
Create and activate a virtual environment:

macOS/Linux:

Bash

python3 -m venv .venv
source .venv/bin/activate
Windows:

Bash

python -m venv .venv
.
.venv\Scripts\activate
Install the required packages:

Bash

pip install -r requirements.txt
▶️ Running the Application
Once installed, you can run the app locally using Uvicorn's development server, which includes auto-reload.

Bash

uvicorn main:app --reload
The server will start on http://127.0.0.1:8000.

📚 API Documentation
While the server is running, you can access the interactive (Swagger UI) API documentation to test the endpoint directly from your browser:

http://127.0.0.1:8000/docs

🛠️ API Endpoint
POST /identify
This is the main endpoint for reconciling contact identities. It finds existing contacts, links them, and creates new contacts as needed.

URL: /identify

Method: POST

Request Body (JSON): (Note: At least one of email or phoneNumber must be provided.)

JSON

{
  "email": "user@example.com",
  "phoneNumber": "1234567890"
}
Success Response (JSON):

JSON

{
  "contact": {
    "primaryContatctId": 1,
    "emails": ["user@example.com", "secondary@example.com"],
    "phoneNumbers": ["1234567890"],
    "secondaryContactIds": [2]
  }
}
Example cURL Request
Here is an example of how to call the API from your terminal:

Bash

curl -X POST "http://127.0.0.1:8000/identify" \
-H "Content-Type: application/json" \
-d '{"email": "lorraine@hillvalley.edu", "phoneNumber": "123456"}'
