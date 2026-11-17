"""Question definitions for the Nakuru SME e-commerce survey.

Single source of truth: the survey form, the database validation, the data
dictionary export and the analysis all read from this module.
"""

LIKERT_AGREE = [
    ("1", "Strongly disagree"),
    ("2", "Disagree"),
    ("3", "Neither agree nor disagree"),
    ("4", "Agree"),
    ("5", "Strongly agree"),
]

LIKERT_CHANGE = [
    ("1", "Strongly decreased"),
    ("2", "Decreased"),
    ("3", "Stayed the same"),
    ("4", "Increased"),
    ("5", "Strongly increased"),
]

DEMOGRAPHICS = [
    {
        "name": "sector",
        "label": "Main sector of the business",
        "type": "select",
        "options": [
            ("retail", "Retail and wholesale trade"),
            ("food", "Food and beverage"),
            ("services", "Services (salon, repair, professional services)"),
            ("manufacturing", "Light manufacturing or agro-processing"),
            ("other", "Other"),
        ],
        "required": True,
    },
    {
        "name": "years",
        "label": "How long the business has been operating",
        "type": "select",
        "options": [
            ("under1", "Less than 1 year"),
            ("1to3", "1 to 3 years"),
            ("4to6", "4 to 6 years"),
            ("7to10", "7 to 10 years"),
            ("over10", "More than 10 years"),
        ],
        "required": True,
    },
    {
        "name": "employees",
        "label": "Number of employees, including the owner",
        "type": "select",
        "options": [
            ("1to9", "1 to 9"),
            ("10to49", "10 to 49"),
            ("50to99", "50 to 99"),
        ],
        "required": True,
    },
    {
        "name": "role",
        "label": "Your role in the business",
        "type": "select",
        "options": [
            ("owner", "Owner"),
            ("manager", "Manager"),
            ("employee", "Employee"),
        ],
        "required": True,
    },
    {
        "name": "location",
        "label": "Where the business is located",
        "type": "select",
        "options": [
            ("cbd", "Nakuru City central business district"),
            ("wakulima", "Around Wakulima Market"),
            ("other_nakuru", "Elsewhere in Nakuru County"),
        ],
        "required": True,
    },
    {
        "name": "channels",
        "label": "Which e-commerce channels does the business use? (select all that apply)",
        "type": "checkbox",
        "options": [
            ("online_store", "Online store or website"),
            ("social", "Social commerce (WhatsApp, Facebook, Instagram, TikTok)"),
            ("payments", "Digital payments (mobile money, card, bank)"),
        ],
        "required": True,
    },
]

SECTIONS = [
    {
        "id": "B",
        "title": "Online stores",
        "instruction": "Think about the business's website or online store. Please indicate how strongly you agree with each statement.",
        "scale": LIKERT_AGREE,
        "items": [
            ("B1", "The business has a website or an online store where customers can view products."),
            ("B2", "Products, prices and availability are displayed online and kept up to date."),
            ("B3", "Customers can place orders through the online store."),
            ("B4", "The online store has increased the number of customers the business serves."),
            ("B5", "The online store allows the business to sell to customers outside Nakuru County."),
            ("B6", "Orders received through the online store are processed and delivered reliably."),
        ],
    },
    {
        "id": "C",
        "title": "Social commerce",
        "instruction": "Think about how the business uses social media and messaging platforms.",
        "scale": LIKERT_AGREE,
        "items": [
            ("C1", "The business uses WhatsApp, Facebook, Instagram or TikTok to promote its products."),
            ("C2", "The business posts or updates product content on social media at least once a week."),
            ("C3", "Customers place orders through social media or messaging apps."),
            ("C4", "The business responds to customer enquiries on social media within a few hours."),
            ("C5", "The business follows up with customers after a sale through social media."),
            ("C6", "Reviews, comments and referrals on social media bring new customers to the business."),
        ],
    },
    {
        "id": "D",
        "title": "Digital payment systems",
        "instruction": "Think about how the business receives payment from customers.",
        "scale": LIKERT_AGREE,
        "items": [
            ("D1", "The business accepts mobile money payments such as M-Pesa."),
            ("D2", "The business accepts card or bank transfer payments in addition to cash."),
            ("D3", "A large share of the business's sales is received through digital payments."),
            ("D4", "Digital payments are settled quickly enough for the daily needs of the business."),
            ("D5", "The business reconciles digital payments against its sales records regularly."),
            ("D6", "Digital payments have reduced the risks and costs of handling cash."),
        ],
    },
    {
        "id": "E",
        "title": "Business performance",
        "instruction": "Compared with three years ago, how has each of the following changed for the business?",
        "scale": LIKERT_CHANGE,
        "items": [
            ("E1", "Sales revenue"),
            ("E2", "Number of customers"),
            ("E3", "Profitability"),
            ("E4", "Market reach, including customers from outside the usual area"),
            ("E5", "Operational efficiency, including time and cost of serving customers"),
            ("E6", "Accuracy and completeness of business records"),
            ("E7", "Speed of responding to customer enquiries"),
            ("E8", "Overall business performance"),
        ],
    },
    {
        "id": "F",
        "title": "Challenges affecting e-commerce adoption",
        "instruction": "Please indicate how strongly you agree that each of the following is a challenge for the business.",
        "scale": LIKERT_AGREE,
        "items": [
            ("F1", "Internet connectivity is unreliable or expensive."),
            ("F2", "Devices and data bundles are too costly for the business."),
            ("F3", "Staff lack the digital skills needed to sell online."),
            ("F4", "Transaction charges on digital payments are too high."),
            ("F5", "Customers do not trust buying online."),
            ("F6", "Cybersecurity and fraud risks are a concern."),
            ("F7", "Delivering goods to online customers is difficult or costly."),
            ("F8", "The business lacks the finance to invest in e-commerce."),
            ("F9", "Regulations, taxes or licensing requirements for online selling are unclear."),
            ("F10", "There is too little time to manage online channels alongside the shop."),
        ],
    },
]

OPEN_QUESTION = {
    "name": "open_challenge",
    "label": "What is the most serious challenge the business faces in using e-commerce?",
    "hint": "Optional. Please do not include names, phone numbers or other personal details.",
}

# Final branching question. "No" finishes the questionnaire; "Yes" reveals a
# details box that must be completed before the form can be submitted.
SOFTWARE_QUESTION = {
    "name": "needs_software",
    "label": "Does the business need a software solution to be developed?",
    "hint": (
        "Choose Yes if the business would like a website, online store, stock system, "
        "booking system or other software built for it. Choose No to finish the questionnaire."
    ),
    "options": [
        ("yes", "Yes"),
        ("no", "No"),
    ],
    "details_name": "software_details",
    "details_label": "What should the software do?",
    "details_hint": (
        "Describe the problem the software should solve and the features needed. "
        "Please do not include names, phone numbers or other personal details."
    ),
    "details_max": 2000,
}

SOFTWARE_LABELS = dict(SOFTWARE_QUESTION["options"])

CHANNEL_LABELS = {
    "online_store": "Online store",
    "social": "Social commerce",
    "payments": "Digital payments",
}

SECTOR_LABELS = dict(DEMOGRAPHICS[0]["options"])
YEARS_LABELS = dict(DEMOGRAPHICS[1]["options"])
EMPLOYEE_LABELS = dict(DEMOGRAPHICS[2]["options"])
ROLE_LABELS = dict(DEMOGRAPHICS[3]["options"])
LOCATION_LABELS = dict(DEMOGRAPHICS[4]["options"])

# Item groups used to build composite scores.
CONSTRUCTS = [
    ("X1", "Online stores", ["B1", "B2", "B3", "B4", "B5", "B6"]),
    ("X2", "Social commerce", ["C1", "C2", "C3", "C4", "C5", "C6"]),
    ("X3", "Digital payment systems", ["D1", "D2", "D3", "D4", "D5", "D6"]),
    ("Y", "SME performance", ["E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"]),
]

TOE_GROUPS = [
    ("Technological", ["F1", "F2", "F4", "F6"]),
    ("Organisational", ["F3", "F8", "F10"]),
    ("Environmental", ["F5", "F7", "F9"]),
]

ALL_ITEMS = [code for section in SECTIONS for code, _ in section["items"]]

ITEM_TEXT = {code: text for section in SECTIONS for code, text in section["items"]}

ITEM_SECTION = {code: section["id"] for section in SECTIONS for code, _ in section["items"]}

SECTION_OF = {section["id"]: section for section in SECTIONS}
