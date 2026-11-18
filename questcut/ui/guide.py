"""Built-in step-by-step lessons."""
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QPushButton, QTextBrowser, QVBoxLayout, QWidget

CSS = """<style>
body { color:#e6e6e6; font-size:13px; }
h2 { color:#ffb648; margin-bottom:4px; }
h3 { color:#ffd54a; margin-bottom:2px; margin-top:12px; }
.k { background:#3a3f4b; border-radius:4px; padding:1px 5px; font-family:monospace; }
.try { background:#22301f; border-left:4px solid #3ddc84; padding:6px; margin-top:8px; }
td { padding:3px 8px 3px 0; }
</style>"""

LESSONS = [
    ("0. Start here: the screen", """
<h2>Welcome to QuestCut</h2>
<p>The window has five areas:</p>
<ol>
<li><b>Left: library.</b> Your files (Media), built-in Game sounds, HUD elements, full-screen Cards and Looks.</li>
<li><b>Middle: preview.</b> The finished movie at the red playhead. Click the picture to play or pause.</li>
<li><b>Right: Inspector.</b> The settings of whatever you clicked. This Guide is the other tab.</li>
<li><b>Bottom: timeline.</b> Time runs left to right. Each row is a <i>track</i>.
Higher video tracks cover lower ones, like stacked photos.</li>
<li><b>Bottom bar:</b> what this computer can do (GPU or not).</li>
</ol>
<p>Default tracks: <b>HUD 2 / HUD 1</b> (game graphics) → <b>V2</b> (GoPro or picture-in-picture) →
<b>V1</b> (main camera) → <b>A1 voice-over</b>, <b>A2 game sounds</b>, <b>A3 music</b>.</p>
<div class='try'><b>Try it:</b> click <b>Create practice project</b> below. It makes two short fake
"camera" videos so you can practise every lesson without touching your real footage.</div>
"""),
    ("1. Import and make your first cut", """
<h2>Import and cut</h2>
<h3>1 · Bring in your files</h3>
<p>Press <span class='k'>Ctrl+I</span> (Mac: <span class='k'>⌘I</span>) or click <b>Import files…</b>.
Pick your GoPro and camera videos. QuestCut makes small preview copies in the background ("preparing
preview…"), so playback stays smooth on a laptop.</p>
<h3>2 · Put a clip on the timeline</h3>
<p><b>Double-click</b> it in the Media list. It lands at the red playhead. You can also <b>drag</b> it onto a track.</p>
<h3>3 · Play</h3>
<p><span class='k'>Space</span> plays and pauses. <span class='k'>←</span> <span class='k'>→</span> step one frame,
<span class='k'>Shift+←/→</span> jump one second. Click the ruler to jump.</p>
<h3>4 · Cut</h3>
<p>Move the red line to where you want to cut and press <span class='k'>S</span> (split).
Click the unwanted piece and press <span class='k'>Delete</span>.
<span class='k'>Shift+Delete</span> also closes the gap.</p>
<h3>5 · Move and trim</h3>
<p>Drag a clip to move it. Drag its <b>left or right edge</b> to make it shorter or longer.
Clips snap to each other and to the playhead (yellow dashed line).</p>
<h3>6 · Copy and paste</h3>
<p><span class='k'>Ctrl+C</span> / <span class='k'>Ctrl+V</span> pastes at the playhead.
<span class='k'>Ctrl+D</span> duplicates. Undo with <span class='k'>Ctrl+Z</span>, as often as you like.</p>
<div class='try'><b>Try it:</b> in the practice project, cut camera A at 00:05, delete the first part, then press
<span class='k'>Ctrl+Z</span> to bring it back.</div>
"""),
    ("2. Two cameras: sync, switch, picture-in-picture", """
<h2>GoPro + camera together</h2>
<h3>1 · Line them up by sound</h3>
<p>Put the camera clip on <b>V1</b> and the GoPro clip of the same scene on <b>V2</b>. Click one, then
<span class='k'>Ctrl</span>+click the other, and press <span class='k'>Y</span> (or right-click → Sync).
QuestCut compares the two soundtracks and slides the GoPro clip until they match.
It also mutes the GoPro's own sound so you don't hear an echo.</p>
<p><i>Tip for filming:</i> a loud clap at the start of each take makes syncing almost perfect.</p>
<h3>2 · Switch between cameras</h3>
<p>Move the playhead to where the view should change and press <span class='k'>A</span>
(<i>Switch camera here</i>). From that point the top camera hides, so you see the other one.
Press <span class='k'>A</span> again later to switch back. Hidden pieces look striped in the timeline.</p>
<h3>3 · Show both at once</h3>
<p>Click the V2 piece and, in the Inspector under <b>Picture-in-picture</b>, choose a corner, or
<b>Minimap circle</b> for a round, game-style mini view. Drag the yellow dot in the preview to move it.</p>
<div class='try'><b>Try it:</b> sync the two practice clips (they start 1.7 s apart), switch at 00:04,
then make the second half a minimap circle.</div>
"""),
    ("3. The game HUD and frame", """
<h2>Game HUD</h2>
<p>Open the <b>HUD</b> tab on the left. Pick a look for new items (<b>Retro pixel</b>, <b>Fantasy RPG</b>,
<b>Shooter / sci-fi</b>). You can mix looks: every item has its own <i>Look</i> setting.</p>
<h3>Add an element</h3>
<p>Double-click e.g. <b>Health / mana / XP bar</b>. It appears on a HUD track at the playhead.
Click it in the timeline: the Inspector shows its settings (label, value, colour…).
<b>Drag the yellow dot</b> in the preview to place it.</p>
<h3>Make it last</h3>
<p>Drag the right edge of the HUD clip in the timeline so it covers the whole scene.</p>
<h3>Screen frame</h3>
<p>Add <b>Screen frame (border)</b> from the <i>Frames</i> group, put it on <b>HUD 2</b> (the top track) and
stretch it over the whole movie. Designs: fantasy gold border, old TV, sci-fi visor, arcade cabinet, minimal corners.</p>
<h3>Useful elements</h3>
<table>
<tr><td><b>Name tag</b></td><td>floats over an NPC; can show a small health bar</td></tr>
<tr><td><b>Dialogue box</b></td><td>types the text letter by letter</td></tr>
<tr><td><b>Quest pop-up</b></td><td>"NEW QUEST: Submit the thesis"</td></tr>
<tr><td><b>Character intro card</b></td><td>name, title, level, stats</td></tr>
<tr><td><b>Score / Timer / Ammo / Minimap</b></td><td>classic corner HUD pieces</td></tr>
<tr><td><b>Pause menu</b></td><td>darkens the screen and shows a menu</td></tr>
</table>
<div class='try'><b>Try it:</b> add a Fantasy RPG health bar top-left, a retro name tag over a "character",
and the Sci-fi visor frame.</div>
"""),
    ("4. Keyframes: make things change over time", """
<h2>Keyframes</h2>
<p>A <b>keyframe</b> remembers a value at one moment. With two keyframes, QuestCut moves the value smoothly
between them. Example: the health bar is 80 at 0:10 and 20 at 0:12, so it drains over two seconds.</p>
<ol>
<li>Click the health bar clip. Move the playhead to where the change <b>starts</b>.</li>
<li>In the Inspector, click the <b>◇</b> next to <i>Value</i>. It turns into <b>◆</b> (a keyframe here).</li>
<li>Move the playhead to where the change <b>ends</b>. Type the new value (e.g. 20).
Because the value already has a keyframe, a new ◆ is added automatically.</li>
<li>Play it. The bar drains, with a white "damage trail" behind it.</li>
</ol>
<p>Keyframes appear as small yellow diamonds on the clip in the timeline. Click ◆ again to delete one.
Use <i>previous / next keyframe</i> in the Inspector to jump between them.</p>
<p>Almost every number can be keyframed: positions (to follow a person), size, opacity, vignette centre,
blur area…</p>
<div class='try'><b>Try it:</b> make the name tag follow a character: add keyframes on Position X/Y at a few
moments, dragging the yellow dot each time.</div>
"""),
    ("5. Spell event: text + sound + hit at once", """
<h2>Casting a spell</h2>
<p>Move the playhead to the moment the spell is cast and press <span class='k'>E</span>
(or HUD tab → <b>⚡ Spell / attack event…</b>). Choose:</p>
<ul>
<li><b>Spell name</b>, e.g. "PEER REVIEW!" or "FIREBALL!"</li>
<li><b>Look</b> and <b>colour</b></li>
<li><b>Cast sound</b> and <b>hit sound</b> (built-in, generated by QuestCut)</li>
<li><b>Hit moment</b>, how long the spell flies</li>
<li><b>Damage</b> and which <b>health bar</b> should drop</li>
</ul>
<p>QuestCut then adds, all lined up:</p>
<ol><li>the spell name with a glowing zoom-in,</li>
<li>a charging swirl and a flying orb from caster (<b>C</b>) to target (<b>T</b>),</li>
<li>the cast sound and the hit sound,</li>
<li>flash + screen shake + damage number at the hit,</li>
<li>the target's health bar dropping exactly at the hit.</li></ol>
<p>Afterwards, click the red spell clip and drag the <b>C</b> and <b>T</b> dots in the preview onto the
caster's hands and the monster.</p>
<h3>Health bar added later?</h3>
<p>No problem. Make all your spells first, then add the health bar. Click the bar in the timeline; in the
Inspector under <b>Spells that hit this bar</b> click <b>Link the spells without a bar</b>. Each spell's
<i>Damage amount</i> is in its own settings, and you can change a spell's target bar there too.</p>
<p>The bar's <i>Value</i> is the health <b>before</b> any spell. Every linked spell takes its damage away at its
hit moment, so if you move a spell, its drop moves with it.</p>
<div class='try'><b>Try it:</b> cast two spells with no bar, then add a Boss bar (Bar type: Boss) and link them.</div>
"""),
    ("6. Freeze-frame character intro", """
<h2>"NPC: The Supervisor, Level 99"</h2>
<ol>
<li>Move the playhead to the frame where the character looks good.</li>
<li>Press <span class='k'>F</span> (or right-click the clip → <b>Freeze frame + character card</b>).</li>
<li>QuestCut pauses the movie there for 3 seconds (everything after moves later), adds a slight darkening
and a vignette, and puts a <b>Character intro card</b> on top.</li>
<li>Click the card in the timeline and type the name, title, level and stats lines.</li>
</ol>
<p>Change the freeze length by dragging the edge of the frozen piece (❄ in its name).</p>
"""),
    ("7. Sound: camera audio, game sounds, music, voice-over", """
<h2>Sound</h2>
<h3>Camera sound</h3>
<p>Video clips keep their own sound. Click a clip → Inspector → <b>Sound</b>: volume (keyframeable), mute,
fade in/out.</p>
<h3>Game sounds and music</h3>
<p>Open the <b>Sounds</b> tab on the left. Select one and click <b>▶ Listen</b>. Double-click to add it at the playhead.
Music lands on the music track and can <b>loop</b> to any length: just drag its right edge.</p>
<h3>Voice-over</h3>
<p>Press <span class='k'>R</span> (or the 🎙 button). There is a 3-2-1 countdown, then the movie plays silently
while you talk. Click <b>Stop</b>: the recording appears on the voice-over track at the right time.</p>
<h3>Ducking</h3>
<p>The music track is set to <b>go quieter automatically while someone talks</b> on the voice-over track.
Click the track name (left side of the timeline) to change how much.</p>
"""),
    ("8. Looks, vignettes and touch-ups", """
<h2>Looks and filters</h2>
<p>Click a clip, then in the Inspector under <b>Effects &amp; filters</b> click one of the <b>+</b> buttons.
Or open the <b>Looks</b> tab and double-click a look to apply it to the selected clip.</p>
<table>
<tr><td><b>Colour &amp; light</b></td><td>brightness, contrast, saturation, warm/cool</td></tr>
<tr><td><b>Game look</b></td><td>retro pixel, sepia flashback, night vision, glitch, CRT, VHS, comic, thermal, dreamy</td></tr>
<tr><td><b>Vignette</b></td><td>shape (oval, circle, rectangle), softness, colour, position, size</td></tr>
<tr><td><b>Touch-up area</b></td><td>blur / pixelate / cover / highlight / spotlight one part of the picture</td></tr>
</table>
<h3>A vignette that follows someone</h3>
<p>Add a vignette, drag its yellow dot onto the person, set a ◇ keyframe on <i>Centre X</i> and <i>Centre Y</i>,
move the playhead and drag again. Keyframe <i>Size</i> to zoom the vignette in for a dramatic moment.</p>
<h3>Hide a face, screen or logo</h3>
<p>Add <b>Touch-up area</b> → <i>Blur it</i>, drag the dot onto it, adjust width/height, and keyframe the
centre if it moves.</p>
<h3>One look for everything</h3>
<p>Looks tab → <b>Apply to the whole picture…</b> adds an <i>effect layer</i> on a HUD track that changes
everything below it, for example a sepia flashback over both cameras.</p>
"""),
    ("9. Title screen, Game Over and transitions", """
<h2>Cards and transitions</h2>
<p><b>Cards</b> tab: Title screen, Game over, Level complete, Chapter / world intro, Continue? countdown and
Rolling credits. Double-click to add at the playhead; type your text in the Inspector.</p>
<p><b>Transitions</b>: click a clip → Inspector → <i>Transitions</i>. Set how it starts and ends: cross-fade,
flash, wipe, iris circle (very retro), pixel dissolve, glitch, zoom, slide. A small white triangle on the clip
shows the transition.</p>
"""),
    ("10. Export, and moving between computers", """
<h2>Export</h2>
<p>Press <span class='k'>Ctrl+E</span> or click <b>Export</b>. Tick <b>Quick test</b> to render only 10 seconds,
which is handy for checking a spell scene. The result is a normal MP4 that plays on Mac, Windows, phones and
projectors.</p>
<h3>Working at home on the Mac</h3>
<ol>
<li><b>File → Pack project for another computer…</b> copies the project and all its videos into one folder.</li>
<li>Copy that folder to a USB drive or cloud folder.</li>
<li>On the Mac, open the <code>.questcut</code> file inside it. Everything is found automatically.</li>
</ol>
<p>If you move files yourself and QuestCut can't find them, it asks you for the folder and searches it.</p>
<h3>Joining several projects into one</h3>
<p>If each scene is its own project, use <b>File → Combine projects…</b>. Add the <code>.questcut</code>
files, put them in order with <i>Move up / Move down</i>, choose a gap if you want a pause between scenes, and click
<b>Combine</b>. They're placed one after another in the current project: V1 goes onto V1, HUD 1 onto HUD 1,
and so on. Spells keep hitting their own health bars. Then <b>Save as…</b> under a new name. Your original
scene projects are not changed.</p>
<h3>Fast export on the lab GPU computer</h3>
<p>Open the same packed folder on the Linux machine and export. The bottom bar shows <i>GPU: NVIDIA …</i> and
<i>Export encoder: NVIDIA GPU (NVENC)</i> when the GPU is being used.</p>
"""),
    ("11. Game-inspired elements", """
<h2>Elements that look like famous games</h2>
<p>In the <b>HUD</b> tab, open the groups called <b>Inspired by …</b>. Each name says which game screen
it imitates, e.g. <i>Parchment level-up box (RuneScape level-up message)</i>. They work like every other HUD
element: double-click to add, drag the yellow dot, use ◇ to animate numbers.</p>
<table>
<tr><td><b>RuneScape</b></td><td>parchment level-up box, damage splats, wavy/flashing chat text, XP drops</td></tr>
<tr><td><b>Stardew Valley</b></td><td>level-up profession choice, item pop-up, message box, day/time/gold clock, energy bar</td></tr>
<tr><td><b>Skyrim</b></td><td>"SKILL INCREASED TO 47", health/magicka/stamina bars, compass with enemy health,
corner messages, subtitles, starry skills screen, inventory, four-way menu</td></tr>
<tr><td><b>Elden Ring</b></td><td>rest menu, big gold/red banner, boss health bar, thin compass, item obtained</td></tr>
<tr><td><b>Other classics</b></td><td>Zelda hearts, Pokémon HP box and battle text, Street Fighter versus bars,
Minecraft achievement toast and XP bar</td></tr>
</table>
<h3>Stardew-style conversations</h3>
<p>HUD → <i>Inspired by Stardew Valley</i> → <b>Dialogue box with portrait</b>. The text types itself in a wooden
box at the bottom, and the speaker's face sits in a frame on the right with their name underneath.</p>
<ol>
<li>Put the box where the person starts talking and type their line and name.</li>
<li>Move the red playhead to a moment where the speaker's face is clearly visible and click
<b>Grab portrait from the current frame</b> (Inspector).</li>
<li>Drag the yellow <b>face</b> dot in the preview onto their face, and use <i>Face zoom</i> to frame it.
<i>Pixel-art portrait</i> makes it blocky like the game.</li>
<li>For the next line, add another box (or cut this one with <span class='k'>S</span>), change the text and
name, and grab a new portrait. That's how you change expression or speaker.</li>
</ol>
<p>Add the <b>Text blip</b> sound (Sounds → Menus &amp; text) when each box appears. To stop the Stardew clock
during a conversation, cut the clock there and set <i>Game minutes per second</i> to 0 for that piece.</p>
<h3>A RuneScape quest: talk, fight, reward</h3>
<p><b>1 · The quest is given.</b> Put the playhead where the NPC starts talking and press <span class='k'>Q</span>
(or HUD tab → <b>📜 Quest talk…</b>). Type what the NPC says (each line becomes its own chat box), the answers to
choose from, and which answer you pick. You get: the parchment chat box at the bottom with the NPC's name in dark
red and blue "Click here to continue"; the <b>Select an Option</b> list where your answer lights up white; your
reply in a box with your head on the right; the red "You have started a new quest" message; blip and select
sounds; the warm 'Quest giver' music under it and the 'Quest accepted' jingle. To show the NPC's face in the box: select the box → <i>Face picture</i> →
grab it from the video, exactly like the Stardew portrait.</p>
<p><b>2 · The fight.</b> Press <span class='k'>K</span> (or <b>⚔ Fight…</b>). Give both fighters a name, their
health and their biggest hit. You get a small green-over-red <b>health bar above each head</b>, then turns of
attacks: a red damage splat (or a blue <b>0</b> for a miss) lands on a fighter, their bar drops by exactly that
number, a hit sound plays and an XP drop floats in the top-right for your hits. The opponent always loses, you
always survive, and "You have defeated …" appears at the end. Then <b>drag each bar's yellow dot over the
fighter's head</b>. If they move, keyframe the bar's X and Y. The splats follow their bar on their own.
Don't like the random numbers? Undo and press <span class='k'>K</span> again; or click a splat and type a new
number (the bar follows).</p>
<h3>Music for quests</h3>
<p>The Sounds tab has two sets of orchestral music made by QuestCut itself (no copyright problems), each with
a ▶ Listen button. Music pieces repeat seamlessly for as long as you stretch them on the timeline.</p>
<p><b>Medieval quest (RuneScape-like):</b> <i>Quest giver</i> (warm village tune, flute and lute) ·
<i>Quest accepted</i> (short jingle) · <i>Setting off</i> (hopeful travelling) · <i>Tavern jig</i> ·
<i>Sneaking</i> (pizzicato tiptoe) · <i>Battle: drums and horns</i> · <i>Quest complete: big fanfare</i>.</p>
<p><b>Dark fantasy (Elden Ring-like):</b> <i>Monster steals the treasure</i> (driving danger music) ·
<i>Dread</i> (short shock when something terrible happens) · <i>Dark boss</i> (choir and war drums) ·
<i>Enemy felled</i> (short golden swell after a big win) · <i>Resting place</i> (calm, sad) · <i>Lament</i>
(loss and sorrow).</p>
<p>A quest scene could run: Quest giver → Quest accepted → Setting off → Dread (the monster appears) →
Monster steals the treasure → Dark boss → Enemy felled → Quest complete fanfare. Overlap the end of one piece
with the start of the next and give both a fade (right panel) so they blend.</p>
<p><b>3 · The reward.</b> HUD tab → RuneScape group → <b>Quest complete scroll</b>: quest name, item icon, reward lines
(they appear one by one) and fireworks. Add the <b>Quest complete</b> sound and, under it, <b>Chat-box game
messages</b> for "Congratulations! Quest complete!". In those messages, <i>[red]</i>, <i>[blue]</i>,
<i>[purple]</i>… change the colour of what follows.</p>
<p><b>Cameras:</b> RuneScape looks down at the characters from above. Use Camera A (high, wide) for the quest and
the reward. For the fight, keep Camera A full screen and put the GoPro in a corner (Camera → Picture-in-picture →
top-left; the top-right is where the XP drops go). Cut to the GoPro full screen for one or two big hits, or for
the moment you pick your answer.</p>
<h3>Creature battles (Pokémon style)</h3>
<p>Press <span class='k'>B</span> (or HUD tab → <b>⚔ Battle start…</b>) at the moment the battle should begin.
In one go you get the battle-start transition (flashes + spiral/stripes/blocks, or name bands with VS), the jingle,
both HP boxes sliding in, "A wild … appeared!", the FIGHT / BAG / TEAM / RUN menu and looping battle music.
Then press <span class='k'>E</span> for attacks: choose the enemy's HP box as the target and its bar drains,
turning yellow, then red.</p>
<p>Press <span class='k'>C</span> for a <b>catch</b>: a sample tube is thrown, flashes, drops, wobbles up to three
times, then either "Gotcha!" with stars or a burst when it breaks free. Drag the <b>T</b> dot onto the person.</p>
<h3>More creature-collecting moments</h3>
<p><b>Who's that …?</b> Press <span class='k'>W</span>. Pick the picture: the video frame at the red line, or any
picture file. The person is cut out of the background automatically and shown as a black silhouette on blue rays
with your question and a sting; at the reveal time there's a white flash, the real picture, "It's …!" and a
fanfare. Drag the yellow <b>person</b> dot onto them and set <i>Picture zoom</i> so the square holds only them.
The automatic cut-out works best on a plain background. On a busy one, use a PNG with a transparent background, or
give your own black shape as <i>Own shadow picture</i>.</p>
<p><b>Evolution:</b> Press <span class='k'>V</span>. "What? … is evolving!", the person glows white and flickers
between the before and after pictures faster and faster, a flash, the new form and "Congratulations!". The ending
can also be <i>stops</i>: "Huh? … stopped evolving!". The after picture has its own dot and zoom.</p>
<p><b>Index entry</b> (HUD tab → creature group): a red handheld index with the picture being scanned in, number,
name, "The … Creature", two type labels, height, weight and a typed description. <b>Badge received</b>: a shiny
badge (choose shape and colour) and "… received the … Badge!". New sounds for all of these are under Sounds →
Creature battle.</p>
<p>Also in the group: a four-move menu with PP and type, status tags (PAR, SLP, …), the player box with a blue EXP
bar (keyframe <i>EXP</i> to fill it), and a level-up stats window that shows the gains, then the totals.</p>
<p><b>Camera:</b> film from behind your fighter (their back at the bottom-left) with the opponent facing the camera.
That's the classic battle view. For "fainted", let the actor fall over dramatically and add
"REVIEWER 2 fainted!" in a battle message box.</p>
<h3>Match the camera view</h3>
<p>They look most convincing on footage filmed like the game:
<b>GoPro / first person</b> → Skyrim or Minecraft;
<b>behind the back</b> → Elden Ring or Zelda;
<b>high angle looking down</b> → Stardew Valley or RuneScape;
<b>side view / face-off</b> → Street Fighter or Pokémon.</p>
<h3>Spells hit these bars too</h3>
<p>Boss bars, HP boxes, hearts, versus bars, the compass enemy bar and the Skyrim health bar can all be linked to
spells (Inspector → <i>Spells that hit this bar</i>). For hearts, the damage counts in hearts.</p>
<h3>Animating menus</h3>
<p>Menus (rest menu, inventory, skills screen) have a <i>Selected</i> number. Keyframe it (◇) from 0 to 3 and the
highlight slides down the list, as if someone is scrolling.</p>
<div class='try'><b>Try it:</b> put the Skyrim compass and bars over the GoPro clip, then add
"SKILL INCREASED" when the character picks up the pipette.</div>
"""),
    ("12. Big edits: insert, remove time, select many, groups", """
<h2>Edits that move the whole movie</h2>
<h3>Insert a clip in the middle (everything after it moves)</h3>
<p>Click <b>⇥ Insert mode</b> in the toolbar (or press <span class='k'>Ins</span>) so it stays pressed.
Now when you drop a camera clip, picture or card in the middle of the movie, everything after that point, on
<b>every</b> track, moves later to make room: sounds, spells, HUD, music. A clip that was playing at that point is
cut in two. HUD elements, effect layers and looping music are not cut; they get longer instead, so a frame or a
health bar keeps going over the new part. Paste (<span class='k'>Ctrl+V</span>) works the same way.
Click the button again to switch it off.</p>
<p><b>Insert empty time:</b> Edit → <i>Insert empty time at playhead</i> (<span class='k'>Ctrl+Shift+T</span>)
pushes everything after the red line later by the number of seconds you type.</p>
<h3>Remove a stretch of time from everything</h3>
<ol>
<li>Mark it: press <span class='k'>I</span> at the start and <span class='k'>O</span> at the end, or hold
<span class='k'>Shift</span> and drag along the time ruler at the top. The stretch turns blue.</li>
<li>Press <span class='k'>Ctrl+Shift+Delete</span> (or right-click → <i>Remove the marked … s</i>).</li>
</ol>
<p>That stretch disappears from every track and everything after it slides left: no gaps, nothing out of sync.
Animations on both sides of the cut stay exactly as they were. Locked tracks (🔒) are left alone.
Without marks, it removes the time covered by the selected pieces. <span class='k'>Alt+X</span> clears the marks.</p>
<h3>Select many pieces</h3>
<p>Drag on an empty part of the timeline to draw a box: everything it touches is selected. Hold
<span class='k'>Ctrl</span> to add to what is already selected. Then drag any of them to move them all, or press
<span class='k'>Delete</span>. A plain click on an empty part still moves the red line. (To scrub, drag in the
time ruler at the top.)</p>
<h3>Groups</h3>
<p>Select pieces and press <span class='k'>G</span>. They get a coloured stripe and a ⛓. Clicking one selects
the whole group, and dragging moves them together. <span class='k'>Shift+G</span> ungroups.
<span class='k'>Alt+click</span> picks just one piece in a group, for example to change one damage number.</p>
<p>All one-click sequences (spell, battle, catch, quest talk, fight, Who's that, evolution) come out as a group,
so you can move a whole fight with one drag.</p>
<div class='try'><b>Try it:</b> mark 2 seconds in the middle of the practice movie with Shift+drag on the ruler and
press Ctrl+Shift+Delete. Then press Ctrl+Z, switch on Insert mode and drop the GoPro clip at the same place.</div>
"""),
    ("13. Keyboard shortcuts", """
<h2>Shortcuts</h2>
<table>
<tr><td><span class='k'>Space</span></td><td>Play / pause</td></tr>
<tr><td><span class='k'>← →</span></td><td>One frame back / forward</td></tr>
<tr><td><span class='k'>Shift+← →</span></td><td>One second back / forward</td></tr>
<tr><td><span class='k'>Home / End</span></td><td>Start / end of movie</td></tr>
<tr><td><span class='k'>S</span></td><td>Split (cut) at playhead</td></tr>
<tr><td><span class='k'>Delete</span> / <span class='k'>Shift+Delete</span></td><td>Delete / delete and close gap</td></tr>
<tr><td><span class='k'>Ins</span></td><td>Insert mode on / off</td></tr>
<tr><td><span class='k'>I</span> / <span class='k'>O</span></td><td>Mark start / end of a stretch of time</td></tr>
<tr><td><span class='k'>Ctrl+Shift+Delete</span></td><td>Remove the marked time from every track</td></tr>
<tr><td><span class='k'>Ctrl+Shift+T</span></td><td>Insert empty time at the playhead</td></tr>
<tr><td><span class='k'>G</span> / <span class='k'>Shift+G</span></td><td>Group / ungroup</td></tr>
<tr><td><span class='k'>Ctrl+G</span></td><td>Close the gap at the playhead</td></tr>
<tr><td><span class='k'>B</span> / <span class='k'>C</span> / <span class='k'>W</span> / <span class='k'>V</span></td><td>Battle start / catch / Who's that…? / evolution</td></tr>
<tr><td><span class='k'>Ctrl+C / V / D</span></td><td>Copy / paste / duplicate</td></tr>
<tr><td><span class='k'>Ctrl+Z / Ctrl+Shift+Z</span></td><td>Undo / redo</td></tr>
<tr><td><span class='k'>A</span></td><td>Switch camera here</td></tr>
<tr><td><span class='k'>Y</span></td><td>Sync the selected clips by sound</td></tr>
<tr><td><span class='k'>F</span></td><td>Freeze frame + character card</td></tr>
<tr><td><span class='k'>E</span></td><td>Spell / attack event</td></tr>
<tr><td><span class='k'>Q</span> / <span class='k'>K</span></td><td>Quest conversation / fight (RuneScape style)</td></tr>
<tr><td><span class='k'>R</span></td><td>Record voice-over</td></tr>
<tr><td><span class='k'>H</span></td><td>Hide / show the selected piece</td></tr>
<tr><td><span class='k'>Z</span></td><td>Zoom timeline to fit · <span class='k'>Ctrl+wheel</span> zoom</td></tr>
<tr><td><span class='k'>Ctrl+I / S / E</span></td><td>Import / save / export</td></tr>
</table>
<p>On a Mac, use <span class='k'>⌘</span> instead of Ctrl.</p>
"""),
]


class Guide(QWidget):
    def __init__(self, mw):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(4, 4, 4, 4)
        row = QHBoxLayout()
        self.combo = QComboBox()
        for title, _ in LESSONS:
            self.combo.addItem(title)
        row.addWidget(self.combo, 1)
        nxt = QPushButton("Next ▶")
        nxt.clicked.connect(lambda: self.combo.setCurrentIndex(min(len(LESSONS) - 1, self.combo.currentIndex() + 1)))
        row.addWidget(nxt)
        v.addLayout(row)
        self.text = QTextBrowser()
        self.text.setOpenExternalLinks(True)
        v.addWidget(self.text, 1)
        demo = QPushButton("Create practice project")
        demo.setObjectName("primary")
        demo.clicked.connect(mw.create_practice_project)
        v.addWidget(demo)
        self.combo.currentIndexChanged.connect(self.show_lesson)
        self.show_lesson(0)

    def show_lesson(self, i):
        self.text.setHtml(CSS + LESSONS[i][1])
