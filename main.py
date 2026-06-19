import os
import json
import sqlite3
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types
from pydantic import BaseModel

# 1. Initialize the FastAPI application
app = FastAPI(title="AI Calendar API")

# 2. Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://calendar-ai-frontend.vercel.app", "http://localhost:3000"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Phase 3: Database Setup ---
# This creates a local file called calendar.db and sets up our table automatically
def init_db():
    conn = sqlite3.connect("calendar.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            start_datetime TEXT NOT NULL,
            end_datetime TEXT NOT NULL,
            description TEXT
        )
    ''')
    conn.commit()
    conn.close()

# Run the database setup immediately when the server starts
init_db()

# 3. Initialize the Gemini Client
client = genai.Client()

# --- Define Data Blueprints ---
class CalendarEvent(BaseModel):
    title: str
    start_datetime: str  
    end_datetime: str
    description: str

class EventList(BaseModel):
    events: list[CalendarEvent]

# --- API Endpoints ---

@app.get("/")
def read_root():
    return {"message": "Backend server is running successfully!"}

# NEW ENDPOINT: Fetch all saved events from the database
@app.get("/events/")
def get_events():
    try:
        conn = sqlite3.connect("calendar.db")
        conn.row_factory = sqlite3.Row  # Makes rows act like dictionaries
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM events")
        rows = cursor.fetchall()
        conn.close()
        
        events = [dict(row) for row in rows]
        return {"status": "success", "data": events}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# UPDATED ENDPOINT: Now saves to the database after extracting
@app.post("/upload-event-image/")
async def process_image(file: UploadFile = File(...)):
    try:
        image_bytes = await file.read()
        print(f"Processing {file.filename} with Gemini...")
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type=file.content_type, 
                ),
                "Extract all schedules, deadlines, or events from this image. Format the response strictly to match the requested schema. Use ISO 8601 format for dates (YYYY-MM-DDTHH:MM:SS)."
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=EventList,
            ),
        )

        extracted_data = json.loads(response.text)
        
        # --- NEW: Save the extracted events to our SQLite database ---
        conn = sqlite3.connect("calendar.db")
        cursor = conn.cursor()
        
        saved_events = []
        for event in extracted_data["events"]:
            cursor.execute('''
                INSERT INTO events (title, start_datetime, end_datetime, description)
                VALUES (?, ?, ?, ?)
            ''', (event["title"], event["start_datetime"], event["end_datetime"], event["description"]))
            
            # Attach the new database ID back to the event
            event["id"] = cursor.lastrowid
            saved_events.append(event)
            
        conn.commit()
        conn.close()
        
        return {
            "status": "success", 
            "message": "Events extracted and saved to database!",
            "data": saved_events
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))