"""
Test script for the improved event classification system.
"""
import json
from filtering import classify_content, RELEVANCE_THRESHOLD, CATEGORIES

# Sample test events - some relevant, some irrelevant
test_events = [
    # Should be classified as "indoor playground"
    {
        "title": "AIRZONE - World's First Indoor Atrium Net Playground",
        "description": "AIRZONE is the world's first indoor atrium net playground. It features bouncy nets that span levels 2 to 6 of the mall atrium, slides to connect one level to the next.",
        "venue_name": "AIRZONE"
    },
    # Should be classified as "outdoor playground"
    {
        "title": "Jacob Ballas Children's Garden at Bukit Timah",
        "description": "The Jacob Ballas Children's Garden is the first garden in Asia dedicated to children. The garden offers exploration, adventure and play, with a farm, an orchard, and a forest with its own stream and ponds.",
        "venue_name": "Jacob Ballas Children's Garden"
    },
    # Should be classified as "attractions"
    {
        "title": "Singapore Zoo: Wildlife Access and Family Fun",
        "description": "Explore diverse wildlife from around the globe in immersive habitats. The Singapore Zoo offers engaging experiences for families, including animal encounters, feeding sessions, and educational shows.",
        "venue_name": "Singapore Zoo"
    },
    # Should be classified as "kids dining"
    {
        "title": "Baker & Cook Dempsey Playground Reopens!",
        "description": "Baker & Cook Dempsey offers a delightful experience for families with its reopened playground. Enjoy freshly baked goods and coffee while the kids have a blast at the playground.",
        "venue_name": "Baker & Cook Dempsey"
    },
    # Should be classified as "malls"
    {
        "title": "Hip Kids Play Playground at Forum The Shopping Mall",
        "description": "Hip Kids Play playground offers a fun and safe environment at the shopping mall. Just pop by the Information Counter located on Level 2 during mall hours.",
        "venue_name": "Forum The Shopping Mall"
    },
    # Should be IRRELEVANT - corporate office event
    {
        "title": "Annual Corporate Meeting and Networking Event",
        "description": "Join us for our annual corporate networking event. This is a great opportunity for business professionals to connect and share insights.",
        "venue_name": "Business Conference Center"
    },
    # Should be IRRELEVANT - adult fitness
    {
        "title": "Advanced CrossFit Training Workshop",
        "description": "Intensive CrossFit workshop for experienced athletes. Learn advanced techniques and push your limits.",
        "venue_name": "FitZone Gym"
    },
    # Should be IRRELEVANT - nightlife
    {
        "title": "Jazz Night at The Blue Note",
        "description": "Live jazz performances every Friday night. Enjoy cocktails and music in an intimate setting.",
        "venue_name": "The Blue Note Bar"
    }
]

def main():
    print("=" * 80)
    print("TESTING IMPROVED EVENT CLASSIFICATION SYSTEM")
    print("=" * 80)
    print(f"\nRelevance Threshold: {RELEVANCE_THRESHOLD}")
    print(f"\nCategories:")
    for cat_name in CATEGORIES:
        print(f"  - {cat_name}")
    print("\n" + "=" * 80)

    results = []

    for i, event in enumerate(test_events, 1):
        print(f"\n{'=' * 80}")
        print(f"Event {i}: {event['title']}")
        print(f"{'=' * 80}")
        print(f"Description: {event['description'][:100]}...")
        print(f"Venue: {event['venue_name']}")

        # Classify the event
        classification = classify_content(event)

        print(f"\n--- Classification Results ---")
        print(f"Category: {classification['category']}")
        print(f"Confidence: {classification['confidence']:.3f}")
        print(f"Is Relevant: {classification['is_relevant']}")

        if 'all_scores' in classification:
            print(f"\nAll Category Scores:")
            sorted_scores = sorted(
                classification['all_scores'].items(),
                key=lambda x: x[1],
                reverse=True
            )
            for cat, score in sorted_scores:
                marker = "✓" if score >= RELEVANCE_THRESHOLD else " "
                print(f"  {marker} {cat:20s}: {score:.3f}")

        if 'error' in classification:
            print(f"\nError: {classification['error']}")

        results.append({
            "event": event['title'],
            "category": classification['category'],
            "confidence": classification['confidence'],
            "is_relevant": classification['is_relevant']
        })

    # Summary
    print(f"\n\n{'=' * 80}")
    print("SUMMARY")
    print("=" * 80)
    relevant_count = sum(1 for r in results if r['is_relevant'])
    irrelevant_count = len(results) - relevant_count

    print(f"\nTotal Events: {len(results)}")
    print(f"Relevant Events: {relevant_count}")
    print(f"Irrelevant Events: {irrelevant_count}")

    print("\nRelevant Events by Category:")
    category_counts = {}
    for r in results:
        if r['is_relevant']:
            cat = r['category']
            category_counts[cat] = category_counts.get(cat, 0) + 1

    for cat, count in sorted(category_counts.items()):
        print(f"  {cat:20s}: {count}")

    print(f"\n{'=' * 80}\n")

if __name__ == "__main__":
    main()
