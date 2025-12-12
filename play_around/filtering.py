try:
    from transformers import pipeline
    classifier = pipeline("zero-shot-classification", model="facebook/bart-large-mnli")
    CLASSIFIER_AVAILABLE = True
except ImportError:
    CLASSIFIER_AVAILABLE = False
    classifier = None
    print(classifier)

# Define categories
CATEGORIES = [
    "indoor playground",
    "outdoor playground",
    "kids attractions",
    "malls",
    "kids dining"
]

CATEGORY_HINTS = {
    "indoor playground": ["indoor play", "soft play", "ball pit", "indoor", "playground", "lego", "trampoline"],
    "outdoor playground": ["park", "outdoor", "slide", "sandbox", "water play", "garden play", "camp", "hiking"],
    "kids attractions": ["zoo", "theme park", "museum", "adventure", "escape room", "carnival", "art workshop"],
    "malls": ["mall", "shopping centre", "plaza", "boutique", "retail", "sale", "fashion", "market"],
    "kids dining": ["restaurant", "kids menu", "buffet", "cafe", "baby chair", "high tea", "kids dining"]
}


# Minimum confidence threshold
RELEVANCE_THRESHOLD = 0.35


def normalize_text(text: str) -> str:
    return " ".join(text.replace("\n", " ").split()).strip()


def classify_content(event):
    # Fallback if model not available
    if not CLASSIFIER_AVAILABLE:
        return {
            "category": None,
            "confidence": 0.0,
            "is_relevant": False,
            "scores_ranked": {},
            "raw_text": None
        }

    text_parts = []
    for field, label in [("title", "Title"), ("description", "Description"), ("venue_name", "Venue")]:
        if event.get(field):
            text_parts.append(f"{label}: {event[field]}")

    # Combine and clean text
    raw_text = normalize_text(" ".join(text_parts))

    # If insufficient text, mark irrelevant
    if not raw_text or len(raw_text.split()) < 3:  # edge case: too little content
        return {
            "category": "irrelevant",
            "confidence": 0.0,
            "is_relevant": False,
            "scores_ranked": {},
            "raw_text": raw_text
        }

    try:
        result = classifier(raw_text, CATEGORIES, multi_label=False)

        # Extract top prediction
        top_category = result["labels"][0]
        top_score = result["scores"][0]

        # Sort scores by confidence
        scores_ranked = {
            label: round(score, 4)
            for label, score in sorted(
                zip(result["labels"], result["scores"]),
                key=lambda x: x[1],
                reverse=True
            )
        }
        for cat, keywords in CATEGORY_HINTS.items():
            if any(kw in raw_text.lower() for kw in keywords):
                if scores_ranked.get(cat, 0) < 0.5:  # Boost if low
                    scores_ranked[cat] += 0.1


        # Determine relevance
        is_relevant = top_score >= RELEVANCE_THRESHOLD

        return {
            "category": top_category if is_relevant else "irrelevant",
            "confidence": round(top_score, 4),
            "is_relevant": is_relevant,
            "scores_ranked": scores_ranked,
            "raw_text": raw_text
        }

    except Exception as e:
        return {
            "category": "irrelevant",
            "confidence": 0.0,
            "is_relevant": False,
            "scores_ranked": {},
            "raw_text": raw_text,
            "error": str(e)
        }

def main():
    # Example usage
    test_events = [
        {
            "title": "Fun at the Indoor Playground",
            "description": "Join us for a day of fun at the indoor playground with slides and ball pits.",
            "venue_name": "Happy Kids Indoor Play"
        },
        {
            "title": "Outdoor Adventure",
            "description": "Explore the great outdoors with hiking and camping activities.",
            "venue_name": "Nature Trails"
        },
        {
            "title": "Gourmet Dining for Kids",
            "description": "A special dining experience for kids with healthy and delicious meals.",
            "venue_name": "Kids Gourmet Cafe"
        },
        {
            "title": "Clothing Festival",
            "description": "This event is going to launch first ever clothing brand in history.",
            "venue_name": "City Hall"
        }
    ]

    for event in test_events:
        classification = classify_content(event)
        print(f"Event: {event['title']}")
        print(f"Category: {classification['category']}")
        print(f"Confidence: {classification['confidence']}")
        print(f"Is Relevant: {classification['is_relevant']}")
        print("-" * 40)

if __name__ == "__main__":
    main()