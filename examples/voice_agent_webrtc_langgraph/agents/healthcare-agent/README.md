# Healthcare Telehealth Nurse Agent

This agent is a 24/7 AI voice nurse for existing patients. It authenticates callers, retrieves mock patient profiles (medications, allergies, recent visits), recognizes common symptoms, performs contextual triage using decision rules, offers self‑care guidance, escalates urgent cases, and books appointments. All interactions aim to be clear, compassionate, and brief.

## What it does

- Authenticate the caller (name + DOB + MRN last‑4 or secret answer)
- Look up patient profile, allergies, medications, recent visits, preferred pharmacy
- Recognize symptoms (e.g., "I have a headache") and identify red flags
- Risk stratify and triage (self‑care, soon, urgent) using rules in `mock_data/triage_rules.json`
- Provide tailored advice based on symptoms and medication history
- Escalate urgent cases with clear instructions
- Offer scheduling with available providers from `mock_data/providers.json`
- Confirm preferred pharmacy for prescriptions if needed

## How to use (typical flow)

1. Start by stating your name.
2. Verify identity: provide DOB and either MRN last‑4 or your secret answer. If a secret question is returned, answer it.
3. Describe your symptoms in your own words.
4. The agent will ask brief, focused follow‑ups (one question at a time), provide guidance, and book if needed.

## Example conversation

- Agent: Welcome back to our clinic. I’m your nurse assistant. May I have your full name?
- You: John Marshall.
- Agent: Thanks, John. Please confirm your date of birth and either your MRN last‑4 or answer to your secret question.
- You: January 1st, 1960. MRN last‑4 is 0001.
- Agent: Thank you. You’re verified. What’s going on today?
- You: I have a headache and feel really fatigued.
- Agent: I’m sorry you’re feeling that way. Any red flag symptoms like worst headache of your life, head injury, stiff neck, weakness, vision changes, seizure, or fever over 102°F?
- You: No, none of those.
- Agent: Thanks for checking. You’re on acetaminophen as needed and have a penicillin allergy. Since symptoms are mild with no red flags, try hydration, rest, and acetaminophen as directed. Would you like a telehealth appointment in the next day or two?
- You: Yes, please.
- Agent: I can book with Alex Chang, NP. Next openings are today at 8:00 pm, or tomorrow at 8:30 am or 4:00 pm. Which do you prefer?
- You: Tomorrow at 8:30 am.
- Agent: Booked. I’ll send details to your phone ending in 0101. Should we keep the pharmacy at 1010 El Camino Real, Santa Clara for any prescriptions?
- You: Yes, that’s fine.
- Agent: Great. I’ve logged your symptoms, advice provided, and appointment. If anything worsens—especially fever over 102°F, neck stiffness, confusion, weakness, vision loss, or severe headache—seek urgent care or call emergency services.

## Mock data

- Patients: `mock_data/patients.json`
- Providers: `mock_data/providers.json`
- Pharmacies: `mock_data/pharmacies.json`
- Triage rules: `mock_data/triage_rules.json`

## Notes

- The agent prioritizes empathy and brevity. It asks one question at a time and avoids medical jargon.
- All data are mock fixtures for demo purposes only and are not real medical records.
