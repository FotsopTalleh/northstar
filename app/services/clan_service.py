"""
Clan service — all clan business logic.
"""
import uuid
from datetime import datetime, timezone
from app.firebase import get_db

MAX_CLAN_SIZE = 10
MIN_CLAN_SIZE = 5


def create_clan(leader_id: str, name: str, description: str) -> dict:
    db = get_db()

    # Ensure leader exists and is not in a clan
    leader_ref = db.collection("users").document(leader_id)
    leader = leader_ref.get()
    if not leader.exists:
        raise ValueError("User not found")
    leader_data = leader.to_dict()
    if leader_data.get("clan_id"):
        raise ValueError("You are already in a clan")

    # Clan name uniqueness
    existing = db.collection("clans").where("name", "==", name).limit(1).get()
    if existing:
        raise ValueError("Clan name already taken")

    clan_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    clan_doc = {
        "clan_id": clan_id,
        "name": name,
        "description": description,
        "leader_id": leader_id,
        "member_ids": [leader_id],
        "created_at": now,
        "badges": [],
        "total_xp": leader_data.get("total_xp", 0),
        "avg_xp": leader_data.get("total_xp", 0),
        "status": "forming",  # becomes 'active' once 5 members join
    }
    db.collection("clans").document(clan_id).set(clan_doc)
    leader_ref.update({"clan_id": clan_id})
    return clan_doc


def invite_user(clan_id: str, leader_id: str, invitee_id: str):
    db = get_db()
    clan_ref = db.collection("clans").document(clan_id)
    clan = clan_ref.get()
    if not clan.exists:
        raise ValueError("Clan not found")
    clan_data = clan.to_dict()

    if clan_data["leader_id"] != leader_id:
        raise ValueError("Only the clan leader can invite members")
    if len(clan_data["member_ids"]) >= MAX_CLAN_SIZE:
        raise ValueError("Clan is full (max 10 members)")

    invitee = db.collection("users").document(invitee_id).get()
    if not invitee.exists:
        raise ValueError("Invitee not found")
    if invitee.to_dict().get("clan_id"):
        raise ValueError("This user is already in a clan")
    if invitee_id in clan_data["member_ids"]:
        raise ValueError("User is already a member")

    # Create join invitation notification
    from app.services.notification_service import create_notification
    create_notification(
        invitee_id,
        "clan_invite",
        f"You have been invited to join clan '{clan_data['name']}'!",
        metadata={"clan_id": clan_id, "clan_name": clan_data["name"]}
    )
    return {"message": "Invitation sent"}


def join_clan(user_id: str, clan_id: str):
    db = get_db()
    user_ref = db.collection("users").document(user_id)
    user = user_ref.get()
    if not user.exists:
        raise ValueError("User not found")
    user_data = user.to_dict()
    if user_data.get("clan_id"):
        raise ValueError("You are already in a clan")

    clan_ref = db.collection("clans").document(clan_id)
    clan = clan_ref.get()
    if not clan.exists:
        raise ValueError("Clan not found")
    clan_data = clan.to_dict()

    if len(clan_data["member_ids"]) >= MAX_CLAN_SIZE:
        raise ValueError("Clan is full")
    if user_id in clan_data["member_ids"]:
        raise ValueError("Already a member")

    new_members = clan_data["member_ids"] + [user_id]
    new_total = clan_data.get("total_xp", 0) + user_data.get("total_xp", 0)
    new_avg = new_total / len(new_members)
    new_status = "active" if len(new_members) >= MIN_CLAN_SIZE else clan_data.get("status", "forming")

    clan_ref.update({
        "member_ids": new_members,
        "total_xp": new_total,
        "avg_xp": new_avg,
        "status": new_status,
    })
    user_ref.update({"clan_id": clan_id})
    return {"message": "Joined clan", "clan_id": clan_id}


def leave_clan(user_id: str, clan_id: str):
    db = get_db()
    clan_ref = db.collection("clans").document(clan_id)
    clan = clan_ref.get()
    if not clan.exists:
        raise ValueError("Clan not found")
    clan_data = clan.to_dict()

    if clan_data["leader_id"] == user_id:
        raise ValueError("Transfer leadership before leaving the clan")
    if user_id not in clan_data["member_ids"]:
        raise ValueError("You are not in this clan")

    user_ref = db.collection("users").document(user_id)
    user_xp = user_ref.get().to_dict().get("total_xp", 0)

    new_members = [m for m in clan_data["member_ids"] if m != user_id]
    new_total = max(0, clan_data.get("total_xp", 0) - user_xp)
    new_avg = new_total / len(new_members) if new_members else 0
    new_status = "active" if len(new_members) >= MIN_CLAN_SIZE else "forming"

    clan_ref.update({
        "member_ids": new_members,
        "total_xp": new_total,
        "avg_xp": new_avg,
        "status": new_status,
    })
    user_ref.update({"clan_id": None})
    return {"message": "Left clan"}


def respond_to_invite(user_id: str, notif_id: str, action: str):
    db = get_db()
    notif_ref = db.collection("notifications").document(notif_id)
    notif = notif_ref.get()
    if not notif.exists:
        raise ValueError("Invitation not found")
        
    n_data = notif.to_dict()
    if n_data.get("user_id") != user_id:
        raise ValueError("Unauthorized")
    if n_data.get("type") != "clan_invite":
        raise ValueError("Not an invitation")
    if n_data.get("read"):
        raise ValueError("Invitation already responded to")
        
    metadata = n_data.get("metadata", {})
    clan_id = metadata.get("clan_id")
    if not clan_id:
        raise ValueError("Corrupted invitation metadata")

    # Mark as read first
    notif_ref.update({"read": True})

    if action == "accept":
        # Will raise ValueError if clan is full or user already in clan
        join_clan(user_id, clan_id)
        from app.services.notification_service import create_notification
        create_notification(user_id, "info", f"You joined clan {metadata.get('clan_name', '')}")
        return {"message": "Clan joined successfully"}
    elif action == "decline":
        return {"message": "Invitation declined"}
    else:
        raise ValueError("Invalid action")


def kick_member(leader_id: str, clan_id: str, target_user_id: str):
    db = get_db()
    clan_ref = db.collection("clans").document(clan_id)
    clan = clan_ref.get()
    if not clan.exists:
        raise ValueError("Clan not found")
    clan_data = clan.to_dict()

    if clan_data["leader_id"] != leader_id:
        raise ValueError("Only the clan leader can kick members")
    if leader_id == target_user_id:
        raise ValueError("You cannot kick yourself. Transfer leadership and leave instead.")
    if target_user_id not in clan_data["member_ids"]:
        raise ValueError("User is not in the clan")

    # Fetch user for XP
    user_ref = db.collection("users").document(target_user_id)
    user_xp = user_ref.get().to_dict().get("total_xp", 0)

    # Calculate new stats
    new_members = [m for m in clan_data["member_ids"] if m != target_user_id]
    new_total = max(0, clan_data.get("total_xp", 0) - user_xp)
    new_avg = new_total / len(new_members) if new_members else 0
    new_status = "active" if len(new_members) >= MIN_CLAN_SIZE else "forming"

    clan_ref.update({
        "member_ids": new_members,
        "total_xp": new_total,
        "avg_xp": new_avg,
        "status": new_status,
    })
    user_ref.update({"clan_id": None})
    
    from app.services.notification_service import create_notification
    create_notification(target_user_id, "kicked", f"You have been removed from clan '{clan_data['name']}'.")
    return {"message": "User kicked"}


def transfer_leadership(clan_id: str, current_leader_id: str, new_leader_id: str):
    db = get_db()
    clan_ref = db.collection("clans").document(clan_id)
    clan = clan_ref.get()
    if not clan.exists:
        raise ValueError("Clan not found")
    clan_data = clan.to_dict()

    if clan_data["leader_id"] != current_leader_id:
        raise ValueError("Only the current leader can transfer leadership")
    if new_leader_id not in clan_data["member_ids"]:
        raise ValueError("New leader must be an existing clan member")

    clan_ref.update({"leader_id": new_leader_id})
    return {"message": "Leadership transferred", "new_leader_id": new_leader_id}


def get_clan_profile(clan_id: str) -> dict:
    db = get_db()
    clan_ref = db.collection("clans").document(clan_id)
    clan = clan_ref.get()
    if not clan.exists:
        raise ValueError("Clan not found")
    clan_data = clan.to_dict()

    # Enrich member data
    members = []
    for uid in clan_data.get("member_ids", []):
        u = db.collection("users").document(uid).get()
        if u.exists:
            ud = u.to_dict()
            members.append({
                "user_id": uid,
                "username": ud.get("username"),
                "avatar_color": ud.get("avatar_color"),
                "total_xp": ud.get("total_xp", 0),
                "badges": ud.get("badges", []),
                "is_leader": uid == clan_data["leader_id"],
            })
    members.sort(key=lambda m: m["total_xp"], reverse=True)

    # Battle history
    battles_a = db.collection("clan_battles").where("clan_a_id", "==", clan_id).get()
    battles_b = db.collection("clan_battles").where("clan_b_id", "==", clan_id).get()
    all_battles = [b.to_dict() for b in battles_a] + [b.to_dict() for b in battles_b]
    all_battles.sort(key=lambda b: b.get("start_at", ""), reverse=True)

    leader_data = db.collection("users").document(clan_data["leader_id"]).get().to_dict() or {}

    return {
        **clan_data,
        "members": members,
        "member_count": len(members),
        "leader_username": leader_data.get("username", ""),
        "battle_history": all_battles,
    }
