import os
import sys

# Add the project root to python path to import app modules easily
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv('.env')

from app.firebase import get_db
from app.services.leaderboard_service import update_all_leaderboards

def backfill():
    db = get_db()
    
    users = db.collection("users").get()
    print(f"Found {len(users)} users to backfill.")
    
    count = 0
    for doc in users:
        u = doc.to_dict()
        user_id = u.get("user_id")
        username = u.get("username", "Unknown")
        avatar_color = u.get("avatar_color", "#6C63FF")
        
        try:
            # Updating with xp_delta=0 safely initializes them without altering XP
            update_all_leaderboards(user_id, 0, username, avatar_color)
            count += 1
            print(f"Backfilled user: {username}")
        except Exception as e:
            print(f"Failed to backfill {username}: {e}")
            
    print(f"Successfully processed {count} users.")

if __name__ == "__main__":
    backfill()
