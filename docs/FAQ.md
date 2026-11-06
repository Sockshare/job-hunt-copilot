# FAQ

**Is this free?**
Yes. Open source (MIT). "On my computer" and "No AI" cost nothing. Cloud keys are billed by that company, usually a few cents per job.

**Does it apply to jobs for me?**
No. It helps you prepare. You still apply yourself, with documents you've read and approved.

**Will it make things up on my resume?**
It is told not to, and it shows every change in red and green so you can see exactly what moved. It also warns you if new numbers, years, or names appear that weren't in your original. Small local models occasionally slip — that's why the review view exists. Never send anything you haven't read.

**What does the score mean?**
The share of skills the posting names that your resume also mentions, with required skills counting double. It's a word-overlap number, like resume-screening software uses. It is not a measure of you.

**My score is low but I'm qualified.**
Then the posting uses words your resume doesn't. Look at "Missing from your resume" — if you've done those things, say so in the posting's words. That's the whole trick.

**Do I need a powerful computer?**
No. The analysis is instant on anything. The free local AI (`llama3.2:3b`) runs on an ordinary laptop; a rewrite takes 1–4 minutes. A cloud key is faster and writes better.

**Which local model writes best?**
`qwen2.5:7b` or `llama3.1:8b` if you have 8 GB of RAM. `llama3.2:3b` is fine to start.

**Can it read my resume PDF?**
Yes, if the PDF has real text (most do). Two-column layouts sometimes come out jumbled — paste the text in that case.

**Can I speak my interview answers?**
In Chrome, yes (🎤 button). Be aware that Chrome's speech recognition sends your audio to Google's speech service. The app warns you the first time. Typing keeps everything on your computer.

**Does it work on Windows or Mac?**
Built and tested on Linux. It should run on macOS and Windows with the same three commands (`.venv\Scripts\activate` on Windows), but those aren't tested.

**Where is my data?**
`~/.job_hunt_copilot/`. Delete the folder to remove everything.

**How do I update?**
`git pull` then `pip install -r requirements.txt`.

**Different port / no auto-open browser?**
`python app.py --port 9000` · `python app.py --no-browser`

**I'm a developer — how is it built?**
See [ARCHITECTURE.md](ARCHITECTURE.md) and run `pytest`.
