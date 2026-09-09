HOUSE RULES FOR B-ROLL VOCABULARY  (qm-clip-cutter)

A word in a transcript is mapped to the thing a PHOTOGRAPH of it would be OF.
Every entry you write becomes a cutaway that appears on screen while a finance
or policy show says that word.

FOUR DESTINATIONS. Put each word in exactly one:

1. expand   {word: "search term"}
   A concrete, photographable thing: a place, an object, a process, an
   institution with a building, an activity. THIS IS THE VALUABLE ONE and nouns
   belong here.
   Term style, measured over 11,901 live entries: 3-5 plain English words
   (median 4, hard max 6), lowercase, no punctuation, no brand logos, no
   people's names. It must be a thing a stock library actually has.
     data      -> server room data center racks
     crops     -> combine harvester wheat field
     gunships  -> military helicopter flying sky
     teas      -> tea poured cup teapot table

2. people   {key: ["Display Name", "fallback search term"]}
   ONLY a named human being. The key is lowercase; add the bare surname too when
   it is how people say it ("Powell said"). The fallback is the picture used
   when no usable portrait exists - a head of state falls back to their capital,
   a central banker to their bank, a chief executive to what their company makes.
     powell -> ["Jerome Powell", "federal reserve building washington"]

3. abstract  [word, ...]
   An idea, quality, feeling or process with no physical form: "credibility",
   "momentum", "resilience". These still rank BELOW concrete subjects, which is
   the point of the list - a metaphor must never beat a real thing named in the
   same sentence.

4. not_a_picture  [word, ...]
   Discourse and filler ("yeah", "okay", "anyway"), and generic finance words
   too vague to illustrate ("market", "money", "business", "price"). Nothing
   should ever cut to these.

HARD RULES - breaking one is a defect:

* REUSE AN EXISTING PICTURE WHEN ONE FITS. pictures.txt holds all 2,191 pictures
  already in the library. Every NEW picture string costs a download and disk, so
  only invent one when nothing in that file honestly depicts the word. Reuse is
  normal: 11,901 words currently share 2,191 pictures.
* RELIGIOUS IMAGERY MAY ONLY ANSWER A RELIGIOUS WORD. Never map a secular word to
  a church, cathedral, altar, cross, angel, prayer, priest, temple, mosque or
  synagogue. A real defect shipped from this: "mystery" cut to a cemetery angel.
* NO PEOPLE'S NAMES in an expand term. A name goes in , never in a
  search string, or the library asserts a stock photo IS that person.
* NO SLURS, no imagery of violence against real people, nothing that would put a
  real private individual on screen.
* A word you are UNSURE about goes to abstract or not_a_picture. A wrong picture
  on screen is far worse than no picture - the clip cuts away to something the
  speaker did not mean, and that is the failure mode this vocabulary exists to
  avoid.
* Use the supplied context sentence to disambiguate. "bank" beside a river is
  not "bank" beside a rate. "act" as a law is not "act" as performing.
* Do not invent a word that is not in your batch. Do not drop one either -
  every word in the batch must land in exactly one of the four lists.
