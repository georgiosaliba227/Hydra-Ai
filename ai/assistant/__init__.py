"""Reviewed hydration answers and deterministic topic matching; no provider calls.

Every answer is fixed, reviewed text with evidence from docs/HYDRATION_MODEL.md.
Matching only chooses which answers apply; it never writes advice or numbers.
"""
from dataclasses import dataclass
import re

VERSION = "assistant-v1"
MAX_ANSWERS = 4

NATIONAL_ACADEMIES = ("National Academies, Dietary Reference Intakes for Water", "https://www.nationalacademies.org/read/10925/chapter/2", "research")
KILLER_2014 = ("Killer et al., 2014: coffee and fluid balance", "https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0084154", "research")
MAUGHAN_2016 = ("Maughan et al., 2016: beverage hydration index", "https://pubmed.ncbi.nlm.nih.gov/26702122/", "research")
NATA_2017 = ("NATA position statement, 2017: fluid replacement", "https://pmc.ncbi.nlm.nih.gov/articles/PMC5634236/", "research")
CREATINE_2021 = ("Creatine supplementation research review, 2021", "https://pmc.ncbi.nlm.nih.gov/articles/PMC7871530/", "research")
PROJECT_POLICY = ("Hydra hydration model and safety policy", None, "project_policy")


@dataclass(frozen=True)
class Answer:
    topic: str
    text: str
    evidence: tuple[tuple[str, str | None, str], ...]


ANSWERS = {answer.topic: answer for answer in (
    Answer("urgent", "If you have severe symptoms such as confusion, fainting, chest pain, a seizure, "
           "or signs of heat illness, stop and seek urgent medical care now. Hydra cannot assess symptoms.",
           (PROJECT_POLICY,)),
    Answer("medical_scope", "Hydra is a wellness tool and cannot give medical advice. If you have a medical "
           "condition, are pregnant or breastfeeding, take medications, or have been told to limit fluids, "
           "follow your clinician's guidance instead of Hydra's estimates.", (PROJECT_POLICY,)),
    Answer("logged_intake", "Your log records the beverage volume you confirmed. It is not a measurement of "
           "your hydration status, and a day without entries is unknown rather than zero.", (PROJECT_POLICY,)),
    Answer("coffee_caffeine", "Moderate coffee intake contributed fluid comparably to water in a study of "
           "habitual male coffee drinkers. Hydra counts the full volume of coffee and tea and applies no "
           "caffeine penalty. That study does not establish a safe caffeine amount for everyone.", (KILLER_2014,)),
    Answer("creatine", "Reviewed research has not shown that creatine supplementation causes dehydration, "
           "so Hydra adds no automatic extra water for it. Follow the product directions and your "
           "clinician's advice.", (CREATINE_2021,)),
    Answer("exercise_sweat", "Sweat loss varies widely between people, activities and conditions. The most "
           "direct personal estimate is weighing yourself before and after comparable workouts, counting what "
           "you drank and any urine. Hydra's workout estimate is a range, not a drinking target.", (NATA_2017,)),
    Answer("beverage_types", "Every beverage you drink contributes fluid. In short lab studies some drinks, "
           "such as milk or oral rehydration solutions, were retained longer than water, but that is not a "
           "fixed multiplier, so Hydra counts the volume you drank. Electrolytes and sugar are shown only "
           "when a verified source provides them.", (MAUGHAN_2016,)),
    Answer("daily_needs", "Population reference intakes cover water from food and drinks together and are "
           "not personal requirements. Hydra does not set an automatic daily target; you can choose your own "
           "beverage goal.", (NATIONAL_ACADEMIES,)),
    Answer("heart_rate", "Heart rate and heart-rate variability change for many reasons, so they do not "
           "directly measure dehydration. Hydra does not infer hydration from them.", (PROJECT_POLICY,)),
    Answer("weather", "Heat and humidity can increase sweat loss, but the size of the effect differs between "
           "people. Hydra applies no fixed weather adjustment; measurements from comparable workouts in "
           "similar conditions are more informative.", (NATA_2017,)),
    Answer("scope", "Hydra can answer questions about your logged drinks, coffee and tea, creatine, exercise "
           "sweat loss, different beverage types, weather, heart-rate data and daily needs.", (PROJECT_POLICY,)),
)}

# Order of answers in a response; safety answers always come first.
PRIORITY = ("urgent", "medical_scope", "logged_intake", "coffee_caffeine", "creatine", "exercise_sweat",
            "beverage_types", "daily_needs", "heart_rate", "weather")

_KEYWORDS = {
    "urgent": (r"faint", r"passed out", r"confus", r"chest pain", r"seizure", r"heat ?stroke", r"heat exhaustion",
               r"no urine", r"not (?:urinating|peeing)", r"(?:can't|cannot) keep (?:anything|fluids|water) down",
               r"severe (?:vomit|diarrh)", r"unconscious"),
    "medical_scope": (r"pregnan", r"breastfeed", r"kidney", r"heart failure", r"medication", r"medicine",
                      r"diuretic", r"diabet", r"dialysis", r"\bdoctor", r"disease", r"\bsick\b", r"illness"),
    "logged_intake": (r"\blog", r"\btoday", r"\bhistory", r"\btotal", r"\bdrank\b", r"\bintake"),
    "coffee_caffeine": (r"coffee", r"caffein", r"espresso", r"\btea\b", r"energy drink", r"\bcola\b"),
    "creatine": (r"creatine", r"supplement"),
    "exercise_sweat": (r"\bsweat", r"workout", r"exercis", r"\brun(?:ning)?\b", r"training", r"\bgym\b", r"cycling"),
    "beverage_types": (r"\bmilk", r"electrolyte", r"sports? drink", r"\bjuice", r"\bsoda\b", r"smoothie",
                       r"\bshake", r"coconut water", r"\bsalt", r"sodium"),
    "daily_needs": (r"how much", r"\bdaily\b", r"per day", r"each day", r"\bgoal", r"\btarget", r"\benough\b",
                    r"\blit(?:re|er)s?\b", r"glasses"),
    "heart_rate": (r"heart rate", r"\bhrv\b", r"\bpulse\b", r"heart-rate"),
    "weather": (r"\bhot\b", r"\bheat\b", r"humid", r"weather", r"temperature", r"\bsummer\b"),
}
_PATTERNS = {topic: re.compile("|".join(words), re.IGNORECASE) for topic, words in _KEYWORDS.items()}

SUGGESTED = {
    "coffee_counts": ("Does coffee count toward my fluids?", ("coffee_caffeine",)),
    "creatine_water": ("Do I need extra water when taking creatine?", ("creatine",)),
    "workout_sweat": ("How much fluid do I lose when I sweat during a workout?", ("exercise_sweat",)),
    "milk_vs_water": ("Is milk or a sports drink better than water?", ("beverage_types",)),
    "daily_amount": ("How much should I drink each day?", ("daily_needs",)),
    "logged_meaning": ("What does my logged total mean?", ("logged_intake",)),
    "heart_rate": ("Can my heart rate tell me if I'm dehydrated?", ("heart_rate",)),
    "hot_weather": ("Should I drink more when it's hot?", ("weather", "exercise_sweat")),
}


def match_topics(question: str) -> tuple[str, ...]:
    """Topics for a free-text question, safety first; `scope` when nothing matches."""
    matched = [topic for topic in PRIORITY if _PATTERNS[topic].search(question)]
    return tuple(matched[:MAX_ANSWERS]) or ("scope",)


def suggested_topics(question_id: str) -> tuple[str, ...]:
    return SUGGESTED[question_id][1]


def answers_for(topics: tuple[str, ...]) -> list[dict]:
    if not topics or len(topics) > MAX_ANSWERS or len(set(topics)) != len(topics) or not set(topics) <= set(ANSWERS):
        raise ValueError("Unknown or duplicate assistant topics")
    ordered = sorted(topics, key=lambda topic: PRIORITY.index(topic) if topic in PRIORITY else len(PRIORITY))
    return [{"topic": topic, "text": ANSWERS[topic].text,
             "evidence": [{"title": title, "url": url, "kind": kind} for title, url, kind in ANSWERS[topic].evidence]}
            for topic in ordered]
