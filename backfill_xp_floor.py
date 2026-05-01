"""
backfill_xp_floor.py
--------------------
One-shot script: sets total_xp = 0 for every user document where total_xp < 0.
Also syncs the leaderboard entries for those users.

Run once:  python backfill_xp_floor.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.firebase import init_firebase, get_db

def main():
    init_firebase()
    db = get_db()

    users = db.collection("users").get()
    fixed = 0

    for doc in users:
        data = doc.to_dict()
        xp = data.get("total_xp", 0)
        if isinstance(xp, (int, float)) and xp < 0:
            doc.reference.update({"total_xp": 0})
            print(f"  Fixed user {data.get('username', doc.id)}: {xp} -> 0")
            fixed += 1

    print(f"\nDone. Fixed {fixed} user(s).")

    if fixed > 0:
        print("Re-running leaderboard backfill to sync XP changes...")
        from app.services.leaderboard_service import update_all_leaderboards
        users2 = db.collection("users").get()
        for doc in users2:
            data = doc.to_dict()
            try:
                update_all_leaderboards(
                    doc.id, 0,
                    data.get("username", ""),
                    data.get("avatar_color", "#6C63FF")
                )
            except Exception as e:
                print(f"  Leaderboard sync error for {doc.id}: {e}")
        print("Leaderboard sync complete.")

if __name__ == "__main__":
    main()
