import os
import json
import sqlite3
import PyPDF2
import io
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types
from pydantic import BaseModel

app = FastAPI(title="AI Calendar API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://calendar-ai-frontend.vercel.app", "http://localhost:3000"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

init_db()

client = genai.Client()

class CalendarEvent(BaseModel):
    title: str
    start_datetime: str  
    end_datetime: str
    description: str

class EventList(BaseModel):
    events: list[CalendarEvent]

@app.post("/upload-event-file/")
async def process_file(file: UploadFile = File(...)):
    try:
        file_bytes = await file.read()
        
        # Logic for PDF
        if file.filename.endswith(".pdf"):
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
            extracted_text = ""
            for page in pdf_reader.pages:
                extracted_text += page.extract_text() + "\n"
            content_to_send = f"Extract events from this PDF text: {extracted_text}"
        # Logic for Images
        else:
            content_to_send = [
                types.Part.from_bytes(data=file_bytes, mime_type=file.content_type),
                "Extract all schedules, deadlines, or events from this image."
            ]

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=content_to_send,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=EventList,
            ),
        )

        extracted_data = json.loads(response.text)
        
        conn = sqlite3.connect("calendar.db")
        cursor = conn.cursor()
        saved_events = []
        for event in extracted_data["events"]:
            cursor.execute('''
                INSERT INTO events (title, start_datetime, end_datetime, description)
                VALUES (?, ?, ?, ?)
            ''', (event["title"], event["start_datetime"], event["end_datetime"], event["description"]))
            event["id"] = cursor.lastrowid
            saved_events.append(event)
        conn.commit()
        conn.close()
        
        return {"status": "success", "data": saved_events}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))