"""Interactive user profile setup wizard.

Creates `data/user_profile.json` via prompts.
"""
from modules.memory_manager import MemoryManager


def prompt(prompt_text, default=""):
    v = input(f"{prompt_text} ")
    return v.strip() or default


def main():
    mm = MemoryManager()
    print("User profile setup — enter values or press Enter to accept defaults.")

    full_name = prompt("Full name:")
    preferred = prompt("Preferred name:", full_name.split()[0] if full_name else "")
    dob = prompt("Date of birth (YYYY-MM-DD):")
    address = prompt("Home address:")

    contacts = []
    print("Enter primary emergency contact:")
    c_name = prompt("Contact name:")
    c_rel = prompt("Relationship:")
    c_phone = prompt("Phone number:")
    contacts.append({"name": c_name, "relationship": c_rel, "phone_number": c_phone, "is_primary": True, "notes": ""})

    profile = {
        "personal": {
            "full_name": full_name,
            "preferred_name": preferred,
            "date_of_birth": dob,
            "home_address": address,
        },
        "emergency_contacts": contacts,
        "medical": {},
        "daily_routine": {},
        "preferences": {"assistant_name": "Assistant", "speech_rate": "normal", "volume_level": "normal", "reminder_frequency": "normal"}
    }

    mm.save_user_profile(profile)
    print("Saved user profile to data/user_profile.json")


if __name__ == '__main__':
    main()
