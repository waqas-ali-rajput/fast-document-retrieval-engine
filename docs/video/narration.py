"""Generate the voice-over sentence by sentence with edge-tts.

Usage: python narration.py <out_dir>
For every scene NN it writes scene_NN.wav (sentences joined with short pauses) and scene_NN.json:
  {"duration": s, "sentences": [{"start", "end", "text"}], "words": [[start, end, word], ...]}
`text` is the caption (written form); the voice reads the spoken form.
"""
import asyncio
import json
import subprocess
import sys
from pathlib import Path

import edge_tts

VOICE = "en-US-AndrewNeural"
RATE = "-6%"
GAP = 0.28  # pause between sentences, seconds

# Each scene is a list of (spoken text, caption text).
SCENES = [
    [("A student asks a question.", "A student asks a question."),
     ("The answer is hidden somewhere in one hundred and fifty-five university notices.",
      "The answer is hidden somewhere in 155 university notices."),
     ("How do we find it fast, and prove where it came from?",
      "How do we find it fast, and prove where it came from?")],

    [("This is our C S two fifty-one Data Structures and Algorithms project-based learning task.",
      "This is our CS-251 Data Structures and Algorithms project-based learning task."),
     ("From the Department of Computer Systems Engineering, at Mehran University of Engineering and "
      "Technology, Jamshoro, under Doctor Ali Asghar Manjotho.",
      "From the Department of Computer Systems Engineering, MUET Jamshoro, under Dr. Ali Asghar Manjotho."),
     ("Our team: Waqas Ali, Mehran Ali, Gaffar, and Basit Azam.",
      "Our team: Waqas Ali, Mehran Ali, Gaffar and Basit Azam.")],

    [("A RAG assistant, short for retrieval-augmented generation, first retrieves supporting passages, "
      "and then writes an answer.",
      "A RAG assistant (retrieval-augmented generation) first retrieves supporting passages, then writes an answer."),
     ("Our job is the retrieval step.", "Our job is the retrieval step."),
     ("We return the top three passages, each with its passage I D, document, version, date and status.",
      "We return the top 3 passages, each with its passage ID, document, version, date and status."),
     ("And if nothing supports the question, the program must say so.",
      "And if nothing supports the question, the program must say so.")],

    [("The simple method is a linear scan.", "The simple method is a linear scan."),
     ("For every question, read every word of every passage.",
      "For every question, read every word of every passage."),
     ("It works, but the cost grows with the total number of words in the collection.",
      "It works, but the cost grows with the total number of words (T) in the collection.")],

    [("Our engine works as a pipeline.", "Our engine works as a pipeline."),
     ("The tokenizer splits text into lower-case words, removes common stop words, and normalises word endings.",
      "The tokenizer splits text into lower-case words, removes common stop words, and normalises word endings."),
     ("Both search methods use exactly the same rules, so the comparison is fair.",
      "Both search methods use exactly the same rules, so the comparison is fair.")],

    [("We built our own hash table.", "We built our own hash table."),
     ("The F N V one A hash function turns each word into a bucket number.",
      "The FNV-1a hash function turns each word into a bucket number."),
     ("When two words land in the same bucket, that is a collision, and we keep both in a linked list.",
      "When two words land in the same bucket, that is a collision, and we keep both in a linked list."),
     ("This is called separate chaining.", "This is called separate chaining."),
     ("When the table becomes three quarters full, it doubles its number of buckets.",
      "When the table becomes 3/4 full (load factor 0.75), it doubles its number of buckets.")],

    [("Each word points to a postings list: the passages that contain it, and how many times.",
      "Each word points to a postings list: the passages that contain it, and how many times (tf)."),
     ("At query time, we look up only the words of the question, so we visit only their postings, "
      "instead of the whole collection.",
      "At query time we look up only the question's words, so we visit only their postings, not the whole collection.")],

    [("Candidates are scored with B M twenty-five.", "Candidates are scored with BM25."),
     ("Rare words count more, and long passages are normalised.",
      "Rare words count more, and long passages are normalised."),
     ("Then a freshness rule halves the score of superseded notices.",
      "Then a freshness rule halves the score of superseded notices."),
     ("That is why the current twenty twenty-six attendance rule ranks above the old twenty twenty-five one.",
      "That is why the current 2026 attendance rule ranks above the old 2025 one.")],

    [("A passage must match at least half of the question's concepts.",
      "A passage must match at least half of the question's concepts."),
     ("For parking permit for student cars, forty-six passages share a word, but none qualifies.",
      "For \"parking permit for student cars\", 46 passages share a word, but none qualifies."),
     ("So the engine refuses, instead of inventing a rule.",
      "So the engine refuses, instead of inventing a rule.")],

    [("To pick the top k results, we use our own bounded min-heap.",
      "To pick the top-k results, we use our own bounded min-heap."),
     ("Sorting every candidate with merge sort costs more.",
      "Sorting every candidate with merge sort costs more."),
     ("With nine thousand seven hundred candidates, the heap is almost four times faster, with identical results.",
      "With 9,700 candidates, the heap is almost 4× faster, with identical results.")],

    [("The results.", "The results."),
     ("Recall at three is zero point nine one on our twenty labelled questions, and all three unanswerable "
      "questions are refused.",
      "Recall@3 is 0.91 on our 20 labelled questions, and all 3 unanswerable questions are refused."),
     ("The scan and the index return identical answers, but the index is about eleven times faster at one "
      "hundred and fifty-five passages, and fifteen times faster at fifteen thousand five hundred.",
      "Scan and index return identical answers, but the index is about 11× faster at 155 passages, "
      "and 15× faster at 15,500."),
     ("All twenty-four tests pass.", "All 24 tests pass.")],

    [("Here is the real program: the command line, the test suite, and our desktop interface.",
      "Here is the real program: the command line, the test suite, and our desktop interface."),
     ("Every rule in the dataset is synthetic test data, not official university policy.",
      "Every rule in the dataset is synthetic test data, not official university policy.")],

    [("Fast Document Retrieval Engine.", "Fast Document Retrieval Engine."),
     ("Thank you for watching.", "Thank you for watching.")],
]


def run(*args):
    subprocess.run(args, check=True, capture_output=True)


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                          str(path)], capture_output=True, text=True, check=True).stdout
    return float(out.strip())


async def sentence(spoken: str, mp3: Path):
    words = []
    comm = edge_tts.Communicate(spoken, VOICE, rate=RATE, boundary="WordBoundary")
    with open(mp3, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                s = chunk["offset"] / 1e7
                words.append([s, s + chunk["duration"] / 1e7, chunk["text"]])
    return words


async def main(out: Path) -> None:
    tmp = out / "parts"
    tmp.mkdir(parents=True, exist_ok=True)
    for n, scene in enumerate(SCENES, 1):
        t, parts, sentences, words = 0.0, [], [], []
        for k, (spoken, caption) in enumerate(scene):
            mp3 = tmp / f"s{n:02d}_{k}.mp3"
            wav = tmp / f"s{n:02d}_{k}.wav"
            w = await sentence(spoken, mp3)
            run("ffmpeg", "-y", "-v", "error", "-i", str(mp3), "-ar", "48000", "-ac", "1", str(wav))
            d = duration(wav)
            sentences.append({"start": round(t, 3), "end": round(t + d, 3), "text": caption})
            words += [[round(t + a, 3), round(t + b, 3), x] for a, b, x in w]
            parts.append(wav)
            t += d + GAP
        total = t - GAP
        # join sentences with silence gaps
        lst = tmp / f"s{n:02d}.txt"
        sil = tmp / "gap.wav"
        if not sil.exists():
            run("ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", str(GAP),
                str(sil))
        lines = []
        for i, p in enumerate(parts):
            lines.append(f"file '{p.resolve().as_posix()}'")
            if i < len(parts) - 1:
                lines.append(f"file '{sil.resolve().as_posix()}'")
        lst.write_text("\n".join(lines), encoding="utf-8")
        wav = out / f"scene_{n:02d}.wav"
        run("ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(wav))
        (out / f"scene_{n:02d}.json").write_text(
            json.dumps({"duration": duration(wav), "sentences": sentences, "words": words}), encoding="utf-8")
        print(f"scene {n:02d}: {duration(wav):5.1f}s  ({len(scene)} sentences)")


asyncio.run(main(Path(sys.argv[1])))
