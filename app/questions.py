"""Single source of truth for the signup questions.

The form, server-side validation, the admin dashboard and the priority score all read
from these definitions, so changing a question here changes it everywhere.
"""

RADIUS_OPTIONS = [
    ("2", "Within 2 km"),
    ("5", "Within 5 km"),
    ("10", "Within 10 km"),
    ("25", "Within 25 km"),
]

FOR_WHOM_OPTIONS = [
    ("self", "Myself"),
    ("child", "My child"),
    ("household", "Me and my family"),
    ("someone_i_care_for", "Someone I care for"),
]

AGE_BAND_OPTIONS = [
    ("under_2", "Under 2"),
    ("2_17", "2 to 17"),
    ("18_64", "18 to 64"),
    ("65_74", "65 to 74"),
    ("75_plus", "75 or older"),
]

TIME_WITHOUT_DOCTOR_OPTIONS = [
    ("lt_6m", "Less than 6 months"),
    ("6_12m", "6 to 12 months"),
    ("1_2y", "1 to 2 years"),
    ("2_5y", "2 to 5 years"),
    ("5y_plus", "More than 5 years"),
    ("never", "I have never had one in Ontario"),
]

OHIP_OPTIONS = [
    ("yes", "Yes, I have a valid Ontario health card"),
    ("waiting", "I am waiting for my health card"),
    ("no", "No"),
]

HCC_OPTIONS = [
    ("yes", "Yes"),
    ("no", "No"),
    ("not_sure", "Not sure"),
]

LANGUAGE_OPTIONS = [
    ("en", "English"),
    ("fr", "French"),
    ("ar", "Arabic"),
    ("yue", "Cantonese"),
    ("fa", "Farsi (Persian)"),
    ("gu", "Gujarati"),
    ("hi", "Hindi"),
    ("it", "Italian"),
    ("ko", "Korean"),
    ("cmn", "Mandarin"),
    ("pt", "Portuguese"),
    ("pa", "Punjabi"),
    ("ru", "Russian"),
    ("es", "Spanish"),
    ("tl", "Tagalog"),
    ("ta", "Tamil"),
    ("ur", "Urdu"),
    ("other", "Another language"),
]

REFERRAL_OPTIONS = [
    ("", "Choose one (optional)"),
    ("friend_family", "A friend or family member"),
    ("social_media", "Social media"),
    ("community_group", "A community group or settlement agency"),
    ("clinic_pharmacy", "A clinic, pharmacy or hospital"),
    ("search", "Searching online"),
    ("news", "News or a blog"),
    ("other", "Other"),
]

# Optional need questions. Stored only if the person ticks the separate health consent box.
# "group" controls how they are shown and how they are capped in the priority score.
NEED_FLAGS = [
    ("ongoing_condition", "clinical", "An ongoing health condition that needs regular care or prescriptions (for example diabetes, heart disease or asthma)"),
    ("immunocompromised", "clinical", "A weakened immune system (for example from cancer treatment, a transplant or a medical condition)"),
    ("pregnancy", "clinical", "Pregnant, or gave birth in the last 12 months"),
    ("mental_health", "clinical", "A mental health condition that needs ongoing follow-up"),
    ("recent_hospital", "clinical", "A hospital stay, or 2 or more emergency room visits, in the last 12 months"),
    ("serious_illness", "clinical", "A serious or life-limiting illness"),
    ("newcomer", "access", "Arrived in Canada in the last 3 years, including as a refugee"),
    ("disability", "access", "A disability that makes getting care harder"),
    ("language_barrier", "access", "Need care in a language other than English or French"),
    ("no_transport", "access", "No reliable way to get to appointments"),
    ("unstable_housing", "access", "Unstable housing, or at risk of losing housing"),
]

NEED_FLAG_KEYS = {key for key, _, _ in NEED_FLAGS}


def option_keys(options) -> set[str]:
    return {key for key, _ in options}


def label_for(options, key: str) -> str:
    for option_key, label in options:
        if option_key == key:
            return label
    return key
