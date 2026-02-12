import os
from dotenv import load_dotenv
import psycopg2

def test_database_connection():
    """
    Test Supabase database connectivity and basic queries with new schema
    """
    try:
        # Load environment variables
        load_dotenv()
        
        # Get Supabase credentials from environment
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_SERVICE_ROLE')
        
        if not (supabase_url and supabase_key):
            return {
                "success": False,
                "message": "Missing Supabase credentials in environment variables"
            }

        # Extract host and construct connection details from Supabase URL
        # Supabase URL format: https://[project].supabase.co
        db_host = supabase_url.replace('https://', '') 
        
        # Construct connection parameters for Supabase
        conn_params = {
            "host": db_host,
            "port": 5432,  # Supabase default port
            "database": "postgres",  # Supabase default database
            "user": "postgres",  # Using service role
            "password": supabase_key
        }

        # Connect to database
        conn = psycopg2.connect(**conn_params)
        cursor = conn.cursor()
        
        # Test queries to verify schema
        test_queries = [
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'practice_areas'
            );
            """,
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'calendar_event_types'
            );
            """
        ]
        
        results = {}
        for query in test_queries:
            cursor.execute(query)
            result = cursor.fetchone()
            results[query] = result[0]
            
        cursor.close()
        conn.close()
        
        return {
            "success": True,
            "message": "Supabase connection successful",
            "schema_checks": results
        }
        
    except Exception as e:
        return {
            "success": False,
            "message": f"Supabase connection failed: {str(e)}"
        }

if __name__ == "__main__":
    result = test_database_connection()
    print(result)