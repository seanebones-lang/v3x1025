#!/usr/bin/env python3
"""
Generate RAG evaluation dataset using sample data.
Creates test questions with ground truth for RAGAS evaluation.
"""

import json
from pathlib import Path


def generate_evaluation_dataset():
    """Generate evaluation dataset from sample data."""
    
    # Load sample data
    inventory_path = Path("data/sample_inventory.json")
    faqs_path = Path("data/faqs.txt")
    
    eval_data = {
        "questions": [],
        "ground_truths": [],
        "contexts": []
    }
    
    # Inventory-based questions
    if inventory_path.exists():
        with open(inventory_path) as f:
            inventory = json.load(f)
        
        for vehicle in inventory[:3]:
            eval_data["questions"].append(
                f"What is the price of the {vehicle['year']} {vehicle['make']} {vehicle['model']}?"
            )
            eval_data["ground_truths"].append(
                f"${vehicle['price']}"
            )
            eval_data["contexts"].append([
                f"{vehicle['year']} {vehicle['make']} {vehicle['model']}, VIN: {vehicle['vin']}, Price: ${vehicle['price']}, Mileage: {vehicle['mileage']} miles"
            ])
    
    # FAQ-based questions
    faq_questions = [
        {
            "question": "What are your hours of operation?",
            "ground_truth": "Monday-Friday 8:00 AM - 8:00 PM, Saturday 9:00 AM - 6:00 PM, Sunday 10:00 AM - 5:00 PM",
            "context": "Our dealership is open Monday-Friday 8:00 AM - 8:00 PM, Saturday 9:00 AM - 6:00 PM, and Sunday 10:00 AM - 5:00 PM"
        },
        {
            "question": "Do you offer financing?",
            "ground_truth": "Yes, starting at 2.9% APR",
            "context": "We offer competitive financing rates starting at 2.9% APR for qualified buyers"
        },
        {
            "question": "How often should I service my vehicle?",
            "ground_truth": "Oil change every 5,000 miles or 6 months",
            "context": "We recommend oil changes every 5,000 miles or 6 months, tire rotation every 10,000 miles"
        }
    ]
    
    for faq in faq_questions:
        eval_data["questions"].append(faq["question"])
        eval_data["ground_truths"].append(faq["ground_truth"])
        eval_data["contexts"].append([faq["context"]])
    
    # Save evaluation dataset
    with open("eval_dataset.json", "w") as f:
        json.dump(eval_data, f, indent=2)
    
    print("Evaluation dataset generated:")
    print(f"  Questions: {len(eval_data['questions'])}")
    print(f"  Output: eval_dataset.json")
    print("\nSample question:")
    print(f"  Q: {eval_data['questions'][0]}")
    print(f"  A: {eval_data['ground_truths'][0]}")
    
    return eval_data


if __name__ == "__main__":
    generate_evaluation_dataset()

