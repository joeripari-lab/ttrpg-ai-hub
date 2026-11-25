# Star Wars 5e (SW5e) Character & Starship Creation Ruleset & AI Schema

> **System Instructions for Local AI Hub:** 
> Use the rules and constraints defined in **Part 1 (Character Creation)** and **Part 2 (Starship Creation)** below to validate mechanics, calculate modifiers, and populate the empty fields in **Part 3 (Master JSON/Markdown Output Template)**. Ensure all currency is in **Credits (cr)**, weapons are categorized as **Blasters, Vibroweapons, or Lightweapons**, and starship stats strictly adhere to **Size and Tier** locks.

---

## Part 1: Step-by-Step Character Creation Rules

### 1. Concept & Campaign Integration
Define the character's core archetype, alignment (Light, Dark, or Balanced/Gray), and connection to galactic factions (e.g., United Galactic Republic, Capital Federation, Obsidian Ring, or independent crews).

### 2. Choose a Species
Select a species (e.g., Human, Twi'lek, Wookiee, Chiss, Bothan, Sith Pureblood, Talz, or Droid Class I–V).
* **Ability Score Increases (ASI):** Apply racial ASI bonuses (typically +2 to one score and +1 to another).
* **Size & Speed:** Most species are Medium (30 ft. speed); diminutive species (e.g., Ewok, Jawa, Class II Droid) are Small (25 ft. speed) and have restrictions on heavy weapons/shields.
* **Traits & Languages:** Record species traits (e.g., Darkvision, *Rapid Reconstruction* for Droids, *Unarmed Combatant* for Sith Purebloods) and languages (Galactic Basic + species tongue; Droids understand Binary).
* **Physical Characteristics:** Roll or assign Height (`Base + Dice Mod`) and Weight (`Base + [Height Roll x Dice Mod]`).

### 3. Choose a Class
Select a primary class, which determines Hit Dice, proficiencies, starting features, and casting progression:
* **Martial / Specialist Classes:** Berserker, Fighter, Monk, Operative, Scholar.
* **Forcecasters (Uses Force Points [FP]):**
  * *Full Caster:* Consular
  * *Half Casters:* Guardian, Sentinel
  * *Casting Ability:* Wisdom (Light Side powers), Charisma (Dark Side powers), Wisdom or Charisma (Universal powers). *(Variant Rule: Simplified Forcecasting allows picking either WIS or CHA for all powers).*
* **Techcasters (Uses Tech Points [TP]):**
  * *Full Caster:* Engineer
  * *Half Caster:* Scout
  * *Third Caster:* Operative (specific archetypes)
  * *Casting Ability:* Intelligence (requires a tech focus such as a wristpad).

### 4. Determine Ability Scores
Generate the six core attributes (**STR, DEX, CON, INT, WIS, CHA**) using Point Buy (27 points, base 8, max 15 before racial modifiers) or Standard Array (`15, 14, 13, 12, 10, 8`).
* **Point Buy Cost Table:**
  * `8`: 0 pts | `9`: 1 pt | `10`: 2 pts | `11`: 3 pts | `12`: 4 pts | `13`: 5 pts | `14`: 7 pts | `15`: 9 pts
* **Modifier Formula:** $\text{Modifier} = \lfloor (\text{Score} - 10) / 2 \rfloor$

### 5. Choose a Background & Starting Feat
* Select a background (e.g., Scoundrel, Sith Acolyte, Clone, Insurgent, Jensaarai, Jedi).
* Record **2 Skill Proficiencies**, **Tool/Language Proficiencies**, **Background Feature**, and **Personality Characteristics** (Trait, Ideal, Bond, Flaw).
* **SW5e Mandatory Rule:** Every background grants **1 Bonus Feat** at 1st level (e.g., *Brawny, Medic, Charmer, Techie, Crafter, Linguist, Shard Modification, Customized Droid*).

### 6. Equip the Character
Take starting equipment from Class + Background, OR roll starting credits (`1 gp = 10 cr`) to purchase gear:
* **Weapon Categories:** Blasters (ranged, uses power cells), Vibroweapons (melee kinetic), Lightweapons (melee energy, requires specific proficiency).
* **Armor & Shields:** Light, Medium, or Heavy Armor; Light, Medium, or Heavy Shields (shield proficiency is collapsed into the corresponding armor proficiency).
* **Customizations (Droids/Cybernetics):**
  * *Parts (Visible hardware):* Max equal to STR, DEX, or CON modifier (min 1).
  * *Protocols (Internal software):* Max equal to INT, WIS, or CHA modifier (min 1).

### 7. Assign Starship Deployment Role
Characters start at **Deployment Rank 0** (advancing up to Rank 5) and adopt a primary crew station:
* **Pilot:** Maneuvers, flying/turning speed, evasive actions.
* **Gunner:** Fires ship weapons, operates turrets/hardpoints.
* **Mechanic:** Hull patching, shield regeneration, power routing.
* **Operator:** Sensor scans, electronic warfare (Interfere), slicing, comms.
* **Coordinator:** Tactical buffs, issuing orders, inspiring crew.
* **Technician:** System diagnostics, droid/astromech integration, auxiliary power.

---

## Part 2: Step-by-Step Starship Creation Rules

### 1. Starship Scale, Size & Tier
Unlike characters, starships do not have classes; their progression is locked to their **Size Category** and **Tier (0 to 5)**. Newly acquired ships typically start at **Tier 0**.

| Space Size | Ground Scale Equivalent | Tier 0 Stock Cost | Base Mod Capacity | Min Workforce | Typical Crew |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Tiny** | Huge | 10,000 cr | 10 slots | 1 | 1 (Starfighter) |
| **Small** | Gargantuan | 50,000 cr | 20 slots | 2 | 1–2 (Shuttle / Heavy Fighter) |
| **Medium** | Colossal | 100,000 cr | 30 slots | 4 | 2–8 (Light Freighter / Party Ship) |
| **Large** | Colossal | 1,000,000 cr | 50 slots | 10 | 10–100+ (Corvette / Frigate) |
| **Huge** | Colossal | 100,000,000 cr | 60 slots | 100 | 100–1,000+ (Cruiser / Battleship) |
| **Gargantuan**| Colossal | 1,000,000,000 cr | 70 slots | 1,000 | 1,000–10,000+ (Dreadnought) |

### 2. Starship Ability Scores & Crew Crossover
Starships possess **6 Ability Scores** generated via Point Buy (`8` to `15`) plus Size/Role adjustments:
* **Physical Scores (STR, DEX, CON):** Used for hull integrity, shield strength, AC, maneuvering, and physical ship checks. *Crew members use the ship's physical modifiers instead of their own while deployed.*
* **Mental Scores (INT, WIS, CHA):** Represent onboard computers, sensors, and comms/jamming arrays.
  * **Weapon Attacks:** Use the **Player's Proficiency Bonus + Ship's INT Modifier** (unless modified by a Venture like *Precision Gunner*).
  * **Mental Skill Checks:** Crew members use their **own** INT, WIS, and CHA modifiers when deployed, though ship systems may grant bonuses or set save DCs (e.g., $\text{DC} = 8 + \text{Prof.} + \text{Ship's WIS or CHA}$).

### 3. Hull Points (HP) & Shield Points (SP)
* **Hull Points (HP):** Determined by Size Hull Die (e.g., Small = `d6`, Medium = `d8`).
  * *Tier 0 Max HP:* $\text{Max Die Value} + (\text{Average Roll of Remaining Dice}) + (\text{Total Hull Dice} \times \text{Ship CON Mod})$.
* **Shield Points (SP):** Determined by Size Shield Die and installed Shield Generator type (multiplies base shield pool).
  * *Tier 0 Base SP:* $\text{Max Die Value} + (\text{Average Roll of Remaining Dice}) + (\text{Total Shield Dice} \times \text{Ship STR Mod})$.
* **Tier Advancement:** Each tier gained grants additional Hull and Shield Dice (+1 each per tier for Tiny–Large; +2 each per tier for Huge–Gargantuan) and an Ability Score Improvement (+2 to one or +1 to two).

### 4. Role Specialization (Unlocked at Tier 2)
At Tier 2, ships adopt a specialized chassis design:
* **Small Ships:** Bomber, Interceptor, Scout, Scrambler, Shuttle, Strike Fighter.
* **Medium Ships:** Courier, Freighter, Gunboat, etc.
* **Large/Huge Ships:** Battleship, Colonizer, Command Ship, Interdictor, Blockade Ship, Space Station.

### 5. Installing Modifications & Suites
Ships come with stock equipment (Hyperdrive Slot, Navcomputer, basic armor/shields) and vacant **Modification Slots** across five categories:
1. **Engineering (Base 3,500 cr):** Engines, reactors, thrusters, SLAM systems.
2. **Operation (Base 3,500 cr):** Sensors, comms, flight computers, astromech sockets, droid brains, cloaking devices.
3. **Suite (Base 5,000 cr):** Crew quarters, cargo bays, medbays, workshops. *(Requires Small or larger; max suites = $3 + [2 \times \text{Ship CON Mod}]$, min 0).*
4. **Universal (Base 4,000 cr):** Armor plating, shield generators, structural reinforcements.
5. **Weapon (Base 3,000 cr):** Fixed hardpoints, turret hardpoints, laser cannons, torpedo launchers, tractor beams.

---

## Part 3: Master Fillable Template (For Local AI Hub)

```markdown
# SW5e Character & Starship Dossier

## Section A: Character Sheet
* **Character Name:** [AI_FILL]
* **Player / Controller:** [AI_FILL]
* **Species:** [AI_FILL] | **Size:** [Small/Medium] | **Speed:** [25/30] ft.
* **Class & Level:** [AI_FILL] (Level [1])
* **Background:** [AI_FILL] | **Alignment:** [Light / Dark / Gray]
* **Deployment Role & Rank:** [Pilot / Gunner / Mechanic / Operator / Coordinator / Technician] (Rank [0])

### Ability Scores & Saves
| Attribute | Score | Modifier | Saving Throw | Prof? |
| :--- | :---: | :---: | :---: | :---: |
| **STR** | [ ] | [ ] | [ ] | [ ] |
| **DEX** | [ ] | [ ] | [ ] | [ ] |
| **CON** | [ ] | [ ] | [ ] | [ ] |
| **INT** | [ ] | [ ] | [ ] | [ ] |
| **WIS** | [ ] | [ ] | [ ] | [ ] |
| **CHA** | [ ] | [ ] | [ ] | [ ] |

### Combat & Vitals
* **Armor Class (AC):** [ ] ([Equipped Armor + Shield])
* **Hit Points (HP):** [ ] / [ ] | **Hit Dice:** [1dX]
* **Proficiency Bonus:** +2 | **Initiative:** [ ] | **Passive Perception:** [ ]
* **Casting Pool:** [None / Force Points: X / Tech Points: X] | **Save DC:** [ ] | **Attack Mod:** [ ]

### Proficiencies, Features & Feats
* **Skill Proficiencies:** [AI_FILL]
* **Tool & Weapon Proficiencies:** [AI_FILL]
* **Languages:** Galactic Basic, [AI_FILL]
* **Species Traits:** [AI_FILL]
* **Class Features:** [AI_FILL]
* **Background Feature:** [AI_FILL]
* **Starting Feat (from Background):** [AI_FILL]

### Inventory & Credits
* **Credits:** [ ] cr
* **Weapons:**
  1. [Weapon Name] ([Blaster/Vibroweapon/Lightweapon]) | Attack: +[ ] | Damage: [XdY + Mod] [Type] | Properties: [AI_FILL]
  2. [Weapon Name] ([Category]) | Attack: +[ ] | Damage: [XdY + Mod] [Type] | Properties: [AI_FILL]
* **Armor & Gear:** [AI_FILL]
* **Powers Known / Prepared (If Caster):** [AI_FILL]

### Narrative & Personality
* **Physical Description:** Age [ ], Height [ ], Weight [ ], Distinctions: [AI_FILL]
* **Personality Trait:** [AI_FILL]
* **Ideal:** [AI_FILL]
* **Bond:** [AI_FILL]
* **Flaw:** [AI_FILL]
* **Backstory Hook:** [AI_FILL]

---

## Section B: Starship Sheet
* **Vessel Name:** [AI_FILL]
* **Chassis / Model:** [AI_FILL] (e.g., YT-1300f Light Freighter, T-65 X-Wing)
* **Size Category:** [Tiny / Small / Medium / Large / Huge / Gargantuan]
* **Starship Tier:** Tier [0]
* **Role Specialization (Tier 2+):** [None / AI_FILL]
* **Crew Capacity:** Min [ ] / Max [ ] | **Cargo Capacity:** [ ] tons | **Fuel Capacity:** [ ] units

### Starship Ability Scores
| Attribute | Score | Modifier | Saving Throw | Prof? |
| :--- | :---: | :---: | :---: | :---: |
| **STR** (Hull/Shields) | [ ] | [ ] | [ ] | [ ] |
| **DEX** (Maneuvering) | [ ] | [ ] | [ ] | [ ] |
| **CON** (Durability) | [ ] | [ ] | [ ] | [ ] |
| **INT** (Targeting) | [ ] | [ ] | [ ] | [ ] |
| **WIS** (Sensors) | [ ] | [ ] | [ ] | [ ] |
| **CHA** (Comms/Jamming)| [ ] | [ ] | [ ] | [ ] |

### Space Combat Statistics
* **Armor Class (AC):** [ ] ([Armor Type])
* **Hull Points (HP):** [ ] / [ ] | **Hull Dice:** [XdY]
* **Shield Points (SP):** [ ] / [ ] | **Shield Dice:** [XdY] | **Shield Regen Rate:** [ ] / round
* **Flying Speed:** [ ] ft. | **Turning Speed:** [ ] ft.
* **Hyperdrive Class:** Primary Class [ ] | Backup Class [ ]

### Armaments & Hardpoints
1. **[Weapon Name]** ([Fixed / Turret Hardpoint])
   * *Attack Roll:* `1d20 + Crew Prof (+2) + Ship INT Mod ([ ])` = +[ ]
   * *Damage:* [XdY] [Energy/Ion/Kinetic/Explosive] | *Arc:* [Forward/360°] | *Properties:* [AI_FILL]
2. **[Weapon Name]** ([Fixed / Turret Hardpoint])
   * *Attack Roll:* +[ ] | *Damage:* [XdY] [Type] | *Arc:* [AI_FILL]

### Installed Modifications & Suites
* **Modification Slots Used:** [ ] / [Base Capacity by Size]
* **Suites Installed:** [ ] / [Max: 3 + 2x Ship CON Mod]
* **Engineering Systems:** [AI_FILL]
* **Operation Systems:** [AI_FILL]
* **Universal Systems:** [AI_FILL]
* **Suite Systems:** [AI_FILL]

### Crew Assignments & Debt
* **Pilot:** [Character Name] | **Gunner(s):** [Character Name]
* **Mechanic:** [Character Name] | **Operator:** [Character Name]
* **Outstanding Ship Debt / Faction Lien:** [ ] cr owed to [Faction/Lender]
```