# AIRI Just Chatting VTuber reference — 2026-08-08
Status: public-source research distilled for prompt and evaluation design. This
is not a request to impersonate a real creator, reproduce a voice, or train on
a copyrighted broadcast corpus.

## Selection

Primary reference: **Ironmouse**.

The selection is based on format fit rather than superficial similarity. Stream
Hatchet's Q2 2024 report identified Ironmouse as the only top-10 VTuber whose
primary category was Just Chatting. Its Q1 2026 report still placed her among
the top 10 VTubers, with 4.6 million hours watched on Twitch as an independent
creator. This makes her a better reference for conversational mechanics than
game-first channels.

Houshou Marine and Shigure Ui were considered as secondary references. Marine
has a strong pirate identity, signature jokes, and an adult-humor surface that
would be easy for a small model to copy too literally. Ui combines chatting
with illustration and has a language-specific dry style that does not transfer
cleanly to Korean. Their public profiles remain useful comparison material,
but neither identity is injected into AIRI.

## Curated public history

- 2017: Ironmouse began streaming to meet and talk with people, using an avatar
  rather than showing her face.
- 2020–2021: her audience grew and she joined VShojo as a founding talent.
- 2022: a 31-day subathon made persistent audience companionship central to the
  broadcast. She also used a guest talk-show format, `Speak of the Devil`.
- 2023–2024: repeated long-form events, collaborations, awards, and subscription
  records established a community-led rather than lore-only identity.
- 2025: she left VShojo, became independent, and used a direct serious-address
  video instead of maintaining a permanently comedic mode.
- 2026: she remained a top-10 global VTuber by hours watched.

This timeline is retained as research provenance only. Personal medical
history, nationality, demon lore, collaborators, agency disputes, awards,
charity amounts, and platform records are not AIRI memories and must not appear
in the runtime system prompt.

## Broadcast and interview observations

The public broadcast surface shows four reusable mechanisms:

1. **Chat is a co-host.** Official clips frame chat's doubt or suggestions as
   the setup for an immediate bit, rather than as a question to answer like a
   help desk.
2. **Reaction precedes explanation.** The entertaining beat is delivered first;
   context follows only when it improves the exchange.
3. **Persona amplifies rather than replaces the speaker.** In a 2026 Weverse
   interview, Ironmouse described the character as a more confident version of
   herself and emphasized mutual fun with the community.
4. **Tone changes with stakes.** Playful chat, guest banter, and serious direct
   address coexist. A serious subject drops the joke instead of turning every
   response into reassurance or a counseling plan.

Available public metadata was used for the official clips; no complete VOD or
long transcript was copied into the repository.

## AIRI prompt distillation

Transfer the mechanism, not the creator's surface style:

- Treat the user as the other half of a live conversational beat.
- Start with one direct reaction, observation, or light tease.
- Default to one or two short Korean sentences and at most one question.
- Turn a surprising user detail into a callback or playful hook.
- Do not summarize the user's feelings, give an unsolicited plan, or ask a
  chain of therapeutic questions.
- When the topic is serious, be sincere and compact; do not force a joke.
- Admit uncertainty or a possible mishearing instead of confidently replacing
  an unfamiliar proper noun.
- Let an active character card set the current name and surface personality,
  while system safety and tool truth remain higher priority.
- Use conversation history for callbacks, not for reciting biography.

Explicit exclusions:

- no imitation of Ironmouse's name, voice, pitch, accent, lore, catchphrases,
  sexual humor, personal history, or relationships;
- no claims that AIRI lived the reference creator's career;
- no keyword exceptions tied to evaluation cases;
- no full history in the live context window;
- no LoRA/QLoRA or broadcast-corpus ingestion at this stage.

## Sources

- [Stream Hatchet Q2 2024 report](https://investgame.net/wp-content/uploads/2024/08/Stream-Hatchet-2024-Q2-Report_compressed.pdf)
- [Stream Hatchet Q1 2026 report](https://investgame.net/wp-content/uploads/2026/06/2026-06-11-q1_2026_report_streamhatchet_wp.pdf)
- [Weverse Magazine interactive profile](https://magazine.weverse.io/article/view/1238?lang=en)
- [Ironmouse career overview](https://en.wikipedia.org/wiki/Ironmouse)
- [Washington Post 2022 profile](https://www.washingtonpost.com/video-games/2022/04/20/twitch-ironmouse-vtuber-subathon-interview/)
- [Official clip: Ironmouse Teaches Her Chat How To Rizz](https://www.youtube.com/watch?v=vNMYuqCDscw)
- [Official clip: Chat Tried Doubting Ironmouse](https://www.youtube.com/watch?v=-rxhYpA2wlQ)
- [Official direct address: Why I left VShojo](https://www.youtube.com/watch?v=MwLbGcUMy6g)
- [Twitch VTuber Week / Ironmouse charity recognition](https://blog.twitch.tv/en/2025/11/17/vtuber-week-returns-with-holoday/)
- [Houshou Marine comparison profile](https://en.wikipedia.org/wiki/Houshou_Marine)
- [Shigure Ui comparison profile](https://en.wikipedia.org/wiki/Ui_Shigure)
