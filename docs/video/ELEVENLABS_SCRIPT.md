# Fast Document Retrieval Engine — ElevenLabs Voice-Directed Script (timed to the video)

**How to use:** Paste the narration into ElevenLabs. The bracketed directions are performance cues, not words to speak. If your chosen ElevenLabs model reads the cues aloud, remove the cues and use the punctuation and paragraph breaks to guide delivery, or split the script into sections and adjust stability/style settings per section.

**Timing:** this script is fitted to `PBL_video.mp4` (total length 3:50). Each section heading gives the video window for that scene. Each line starts at the timestamp before it (**[m:ss.s]**); that is when the matching animation appears on screen. Each line must finish before the next timestamp. If a line finishes early, leave silence until the next timestamp. Lines are trimmed so that a natural pace (about 150 words a minute) fits each window.

[OVERALL VOICE: Natural, friendly university student. Conversational English, clear pronunciation, confident but not overly dramatic. Medium pace by default. Sound like you're explaining your own project to classmates, not reading a formal announcement.]

## 1. Hook — video 0:00.0 – 0:12.0

[CURIOUS, MEDIUM-SLOW. Start gently; build interest on the question. Pause briefly after “155 university notices.”]

**[0:00.6]** Imagine a student asks a question,

**[0:02.7]** but the answer is buried somewhere in 155 university notices.

[SLIGHTLY SLOWER; EMPHASISE “quickly” and “exactly where it came from.” Pause at the dash.]

**[0:07.7]** How can we find it quickly — and show exactly where it came from?

## 2. Course and team — video 0:12.0 – 0:35.5

[WARM, NORMAL PACE. Friendly introduction. Small pause after “project.”]

**[0:12.6]** Hi everyone! This is our CS-251 Data Structures and Algorithms project-based learning project.

[STEADY, CLEAR. Read the department and supervisor name carefully; don't rush the name.]

**[0:19.3]** We’re from the Department of Computer Systems Engineering at MUET Jamshoro, under the supervision of Dr. Ali Asghar Manjotho.

[NORMAL PACE. Read each name clearly, with a tiny pause between names. Each member's card appears as their name is spoken.]

**[0:29.4]** Our team members are Waqas Ali, Mehran Ali, Gaffar, and Basit Azam.

## 3. What is RAG? — video 0:35.5 – 1:00.4

[CLEAR, TEACHING TONE. Explain “retrieval-augmented generation” slowly the first time. Brief pause before the explanation.]

**[0:36.1]** A RAG assistant — retrieval-augmented generation — first finds useful information in documents, then uses it to write an answer.

[SLIGHT EMPHASIS: “first part” and “finding the right information.”]

**[0:44.5]** Our project is that first part: finding the right information.

[STEADY AND PRECISE. Slow slightly when listing metadata; tiny pauses between items. Each field appears on the evidence card as it is spoken.]

**[0:47.1]** For each question, we return the top three passages, with their passage ID, document, version, date, and status.

[MORE SERIOUS, EMPHASISE THE SAFETY POINT. Pause briefly before “instead of guessing.”]

**[0:55.4]** If there isn’t enough evidence, the program says so instead of guessing.

## 4. Linear scan — video 1:00.4 – 1:14.3

[EXPLANATORY, NORMAL PACE. Slight emphasis on “simple approach.”]

**[1:01.0]** Let’s start with the simple approach: a linear scan.

[PLAIN, CONVERSATIONAL. Explain as if teaching a classmate.]

**[1:03.8]** For every question, it checks every word of every passage.

[SLIGHTLY SLOWER. Emphasise “grows” and clearly say “T.”]

**[1:08.5]** It works, but the time grows with T, the total number of words.

## 5. Pipeline and tokenizer — video 1:14.3 – 1:31.1

[STEADY, EXPLANATORY. Medium pace.]

**[1:14.9]** Our engine follows a pipeline.

[SLOWER AND CLEARER FOR THE TECHNICAL LIST. Tiny pauses between each action.]

**[1:17.2]** First, the tokenizer splits text into lowercase words, removes common stop words, and normalises word endings.

[NORMAL PACE, EMPHASISE “same” and “fairly.”]

**[1:25.3]** Both search methods use the same rules, so we compare them fairly.

## 6. Hash table — video 1:31.1 – 1:54.4

[CONFIDENT, EXPLANATORY. Slight emphasis on “our own hash table.”]

**[1:31.7]** We built our own hash table.

[CAREFUL TECHNICAL DELIVERY. Say “F-N-V one A” clearly; pause briefly after “bucket.”]

**[1:33.9]** It uses the FNV-1a hash to map each word to a bucket.

[EXPLAINING A NEW CONCEPT. Slightly slower; pause after “collision.”]

**[1:39.7]** When two words land in the same bucket, that’s a collision — we keep both in a linked list.

**[1:46.3]** This is called separate chaining.

[NORMAL PACE. Emphasise “75 percent full” and “doubles.”]

**[1:48.5]** And when the table is 75 percent full, it doubles its number of buckets.

## 7. Inverted index — video 1:54.4 – 2:10.0

[TEACHING TONE, MEDIUM-SLOW. Make this sound simple, not overly technical. Slightly slow down for “postings list.”]

**[1:55.0]** Each word points to a postings list: the passages that contain it, and how often.

[BUILD A LITTLE MOMENTUM. Emphasise the contrast with “instead of.”]

**[2:01.2]** So we look up only the question’s words, instead of checking every passage.

## 8. Ranking: BM25 and freshness — video 2:10.0 – 2:29.3

[CAREFUL WITH THE TECHNICAL TERM. Say “B-M twenty-five” clearly.]

**[2:10.6]** To rank the matches, we use BM25.

**[2:13.9]** It gives rare words more weight and adjusts for passage length.

[SLIGHTLY SLOWER. Emphasise “in half.” The SUPERSEDED stamp hits the old notice here.]

**[2:18.2]** Then a freshness rule cuts the score of superseded notices in half.

[ILLUSTRATIVE TONE. Clearly contrast “2026” with “2025.” The two cards swap places here.]

**[2:22.5]** That’s why the current 2026 attendance rule ranks above the old 2025 one.

## 9. Evidence rule — video 2:29.3 – 2:45.0

[MORE SERIOUS, DELIBERATE. This is an important design decision.]

**[2:29.9]** A passage must match at least half of the question’s concepts.

[EXAMPLE-SETTING TONE. Read the quoted question clearly, then pause briefly before the result.]

**[2:34.1]** For “parking permit for student cars,” 46 passages share a word, but none qualifies.

[FIRM BUT CALM. Emphasise “rather than guessing.”]

**[2:40.6]** So the engine refuses rather than guessing.

## 10. Top-k with a bounded heap — video 2:45.0 – 3:01.7

[TECHNICAL BUT ACCESSIBLE. Slightly slower on “bounded min-heap.”]

**[2:45.6]** To pick the best results, we use our own bounded min-heap.

[NORMAL PACE. The comparison bars start growing here.]

**[2:49.9]** Sorting every candidate with merge sort costs more.

[EMPHASISE THE RESULT. Pause briefly before the performance figure.]

**[2:53.6]** With 9,700 candidates, the heap was almost four times faster, with the same results.

## 11. Results — video 3:01.7 – 3:28.3

[TRANSITION WITH A LITTLE ENERGY. Pause after “results.”]

**[3:02.3]** Now, the results.

[PRECISE, MEASURED DELIVERY. Slow down for the metrics; don't overstate them.]

**[3:04.5]** On our 20 labelled questions, Recall at 3 was 0.91, and all three unanswerable questions were correctly refused.

[EMPHASISE THE COMPARISON. Small pause between the two speed figures.]

**[3:13.0]** The linear scan and the inverted index returned the same results, but the index was about 11 times faster with 155 passages, and about 15 times faster with 15,500.

[CONFIDENT, BRIEF. Slight emphasis on “all 24 tests passed.”]

**[3:25.4]** And all 24 tests passed.

## 12. The real program — video 3:28.3 – 3:41.9

[SHOW-AND-TELL TONE. Slightly brighter, normal pace.]

**[3:28.9]** Here’s the actual program: the command line, our test suite, and the desktop interface.

[CAREFUL AND TRANSPARENT. Slow slightly; make the disclaimer easy to hear.]

**[3:35.3]** One note: the dataset is synthetic test data, not official MUET policy.

## 13. Closing — video 3:41.9 – 3:50.0

[WARM, CONFIDENT. Slow down slightly for the project name; finish naturally, not like a dramatic advert.]

**[3:42.5]** And that’s our Fast Document Retrieval Engine.

[FRIENDLY, SIMPLE ENDING. Brief pause before speaking.]

**[3:45.0]** Thanks for watching!
