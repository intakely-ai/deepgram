# law_firm_functions.py (updated database connection)
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv
import urllib.parse

load_dotenv()

# Database connection function using connection string
def get_db_connection():
    # Parse the connection URL
    database_url = os.getenv('DATABASE_URL')
    
    # If using Neon's connection string format
    if database_url:
        # Parse the connection URL
        parsed_url = urllib.parse.urlparse(database_url)
        
        # Extract connection parameters
        dbname = parsed_url.path[1:]  # Remove the leading slash
        user = parsed_url.username
        password = parsed_url.password
        host = parsed_url.hostname
        port = parsed_url.port
        
        conn = psycopg2.connect(
            dbname=dbname,
            user=user,
            password=password,
            host=host,
            port=port
        )
    else:
        # Fallback to individual environment variables
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST'),
            database=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            port=os.getenv('DB_PORT', 5432)
        )
    
    return conn



# Email configuration
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

def save_lead(first_name, last_name, email, phone, source="phone"):
    """Save lead contact information to the database."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO leads (first_name, last_name, email, phone, source) VALUES (%s, %s, %s, %s, %s) RETURNING id;",
            (first_name, last_name, email, phone, source)
        )
        lead_id = cur.fetchone()[0]
        conn.commit()
        return {"status": "success", "lead_id": lead_id, "message": "Lead saved successfully"}
    except Exception as e:
        conn.rollback()
        return {"error": f"Database error: {str(e)}"}
    finally:
        cur.close()
        conn.close()

def update_lead_practice_area(lead_id, practice_area_name):
    """Update the practice area for a lead."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # First, get the practice_area_id from the name
        cur.execute("SELECT id FROM practice_areas WHERE name = %s;", (practice_area_name,))
        practice_area = cur.fetchone()
        if not practice_area:
            return {"error": f"Practice area '{practice_area_name}' not found"}
        
        practice_area_id = practice_area[0]
        cur.execute(
            "UPDATE leads SET practice_area_id = %s, status = 'qualified' WHERE id = %s;",
            (practice_area_id, lead_id)
        )
        conn.commit()
        return {"status": "success", "message": f"Practice area updated to {practice_area_name}"}
    except Exception as e:
        conn.rollback()
        return {"error": f"Database error: {str(e)}"}
    finally:
        cur.close()
        conn.close()

def save_appointment(lead_id, attorney_name, date_time, duration=60):
    """Save an appointment for a lead."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # First, get the attorney_id from the name
        cur.execute("SELECT id FROM attorneys WHERE first_name || ' ' || last_name = %s;", (attorney_name,))
        attorney = cur.fetchone()
        if not attorney:
            return {"error": f"Attorney '{attorney_name}' not found"}
        
        attorney_id = attorney[0]
        cur.execute(
            "INSERT INTO appointments (lead_id, attorney_id, scheduled_time, duration) VALUES (%s, %s, %s, %s) RETURNING id;",
            (lead_id, attorney_id, date_time, duration)
        )
        appointment_id = cur.fetchone()[0]
        
        # Update lead status
        cur.execute(
            "UPDATE leads SET status = 'scheduled' WHERE id = %s;",
            (lead_id,)
        )
        
        conn.commit()
        return {"status": "success", "appointment_id": appointment_id, "message": "Appointment saved successfully"}
    except Exception as e:
        conn.rollback()
        return {"error": f"Database error: {str(e)}"}
    finally:
        cur.close()
        conn.close()

def send_email(to_email, subject, body):
    """Send an email using SMTP."""
    if not all([EMAIL_USER, EMAIL_PASSWORD]):
        return {"error": "Email credentials not configured"}
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = EMAIL_USER
        msg['To'] = to_email
        
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_USER, [to_email], msg.as_string())
        
        return {"status": "success", "message": "Email sent successfully"}
    except Exception as e:
        return {"error": f"Failed to send email: {str(e)}"}

def send_confirmation_email(lead_id, appointment_id):
    """Send a confirmation email for an appointment and log it in the database."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Get lead and appointment details
        cur.execute("""
            SELECT l.first_name, l.last_name, l.email, 
                   a.first_name || ' ' || a.last_name as attorney_name,
                   ap.scheduled_time
            FROM leads l
            JOIN appointments ap ON l.id = ap.lead_id
            JOIN attorneys a ON ap.attorney_id = a.id
            WHERE l.id = %s AND ap.id = %s;
        """, (lead_id, appointment_id))
        
        details = cur.fetchone()
        if not details:
            return {"error": f"Lead or appointment not found"}
        
        first_name, last_name, email, attorney_name, scheduled_time = details
        
        subject = "Appointment Confirmation - Oakwood Law Firm"
        body = f"""
        Dear {first_name} {last_name},
        
        Your appointment with {attorney_name} has been scheduled for {scheduled_time}.
        
        Please arrive 15 minutes early and bring any relevant documents.
        
        Thank you,
        Oakwood Law Firm
        """
        
        # Send the email
        email_result = send_email(email, subject, body)
        if "error" in email_result:
            return email_result
        
        # Log the email in the database
        cur.execute(
            "INSERT INTO email_logs (lead_id, email_type, subject, body) VALUES (%s, %s, %s, %s);",
            (lead_id, "confirmation", subject, body)
        )
        
        conn.commit()
        return {"status": "success", "message": "Confirmation email sent and logged"}
    except Exception as e:
        conn.rollback()
        return {"error": f"Database error: {str(e)}"}
    finally:
        cur.close()
        conn.close()

# Function mapping dictionary for law firm
FUNCTION_MAP = {
    'save_lead': save_lead,
    'update_lead_practice_area': update_lead_practice_area,
    'save_appointment': save_appointment,
    'send_email': send_email,
    'send_confirmation_email': send_confirmation_email
}