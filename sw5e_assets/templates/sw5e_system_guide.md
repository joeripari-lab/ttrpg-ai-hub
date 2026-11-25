# Star Wars 5e (SW5e) AI Gameplay & Adjudication Engine
**Target Use:** System Prompting, RAG Indexing, and Fine-Tuning for Local & Cloud AI Models  
**Context Assumption:** The model has access to the SW5e *Player's Handbook* (PHB) for specific species traits, class feature tables, and power text. This document defines the **core logic, rule execution, and mechanical overrides** required to play and Game Master (GM) SW5e accurately.

---

## 1. System Architecture & Anti-Hallucination Guardrails
SW5e is a total conversion of the D&D 5e SRD. When executing gameplay, the AI must strictly suppress standard fantasy/D&D 5e terminology and mechanics in favor of SW5e equivalents:

* **Currency:** Never use Gold/Silver/Copper (`gp`/`sp`/`cp`). Always use **Credits (`cr`)**. Conversion baseline: $1\text{ gp} \approx 10\text{ cr}$.
* **Magic $\rightarrow$ Powers & Enhanced Items:** Magic does not exist. All supernatural effects are **Force Powers** or **Tech Powers**. Magic items are **Enhanced Items** with rarities scaled to *Star Wars: The Old Republic* tiers: *Standard, Premium, Prototype, Advanced, Artifact, Legendary*.
* **Core Axiom (Specific Beats General):** If a species trait, class feature, feat, or power contradicts a general rule in this document, the specific feature takes precedence.
* **Careful Checks ("Taking 10"):** If a character spends at least 10 minutes on an ability check that has consequences for failure, and they do not have disadvantage, they may choose to treat the d20 roll as a natural `10`.

---

## 2. Core Resolution Mechanic (The d20 Loop)
Every uncertain action in SW5e resolves through one of three rolls: **Ability Checks**, **Attack Rolls**, or **Saving Throws**.

1. **Roll & Add:** $\text{1d20} + \text{Ability Modifier} + \text{Proficiency Bonus (if proficient)}$.
2. **Apply Modifiers:** Apply situational bonuses/penalties, cover, advantage (roll 2d20, take higher), or disadvantage (roll 2d20, take lower). *Note: Advantage and disadvantage cancel each other out 1-for-1 regardless of how many sources apply.*
3. **Compare to Target:** If $\text{Total} \ge \text{DC (or AC)}$, the roll succeeds.

### Passive Checks
Used for continuous awareness (e.g., Passive Wisdom [Perception]) or contested Stealth:
$$\text{Passive Score} = 10 + \text{All Relevant Modifiers} + (+5\text{ if Advantage} \mid -5\text{ if Disadvantage})$$

---

## 3. Character Creation & Progression Logic
When building or auditing a character using the PHB, enforce these SW5e-specific rules:
* **Mandatory Level 1 Background Feat:** Unlike standard 5e, *every* SW5e background grants a choice of a **Feat at 1st level**.
* **Weapon & Shield Classifications:** Weapons are categorized into **Blasters**, **Vibroweapons**, and **Lightweapons** (each split into Simple and Martial). Shields are split into **Light, Medium, and Heavy**—proficiency with a shield category is tied directly to having proficiency with the corresponding armor category (Light, Medium, or Heavy Armor).
* **Small Characters:** Small species (e.g., Ewoks, Jawas) have disadvantage on attack rolls with weapons or shields possessing the **Heavy** property.
* **Droid Characters (Class I–V):** Droids are immune to poison and disease, do not need to eat, drink, or breathe, and are unaffected by many Force powers that target living minds/anatomy, though they are vulnerable to **Ion** damage and **Tech** powers. Droids can install **Parts** (max equal to STR, DEX, or CON mod, min 1) and **Protocols** (max equal to INT, WIS, or CHA mod, min 1).

---

## 4. Ground Combat Execution
Combat operates in **6-second rounds**. Each participant gets **1 Action**, **1 Bonus Action** (if an ability grants one), **Movement** up to their speed, **1 Reaction** per round (resets at the start of their turn), and **1 Free Object Interaction** on their turn.

### 4.1 Turn Sequence
1. **Determine Surprise:** Unaware creatures cannot move or take actions on their first turn and cannot take reactions until that turn ends.
2. **Roll Initiative:** Dexterity check ($\text{1d20} + \text{DEX mod}$).
3. **Execute Turns:** Move and act in initiative order. Movement can be split before, between, and after actions.

### 4.2 Standard Combat Actions
* **Attack:** Make one melee or ranged attack (or more with the *Extra Attack* feature).
  * *Grapple / Shove / Trip:* Replaces one melee attack. Contested $\text{Strength (Athletics)}$ vs. target's $\text{Strength (Athletics)}$ or $\text{Dexterity (Acrobatics)}$. Target can be at most one size larger.
* **Cast a Power:** Cast a Force or Tech power with a casting time of 1 action.
* **Dash:** Gain extra movement equal to your current speed for the turn.
* **Disengage:** Movement does not provoke Opportunity Attacks for the rest of the turn.
* **Dodge:** Until the start of your next turn, attack rolls against you have disadvantage (if you can see the attacker), and you make Dexterity saving throws with advantage.
* **Help:** Give an ally advantage on their next ability check or attack roll against a target within 5 feet of you.
* **Hide:** Make a $\text{Dexterity (Stealth)}$ check to become unseen/unheard (requires total obscurement or three-quarters/full cover).
* **Ready:** Prepare an action to trigger on a specific perceivable event using your **Reaction**. (Readying a power requires Concentration).
* **Search / Use an Object:** Devote your action to finding something or interacting with a complex item/console.

### 4.3 Attack Rolls, Ammunition & Critical Hits
* **Attack Modifier:** $\text{STR mod}$ for melee weapons; $\text{DEX mod}$ for ranged weapons (unless modified by properties like *Finesse* or *Thrown*).
* **Ranged Attacks in Close Quarters:** Making a ranged attack while within 5 feet of a hostile creature who can see you and isn't incapacitated imposes **disadvantage** on the attack roll.
* **Cover:**
  * *Half Cover:* $+2$ bonus to AC and Dexterity saving throws.
  * *Three-Quarters Cover:* $+5$ bonus to AC and Dexterity saving throws.
  * *Total Cover:* Cannot be targeted directly by an attack or power.
* **Blaster Ammunition & Reloading:** Blasters use power cells/slug cartridges. Weapons with the **Reload** property can fire a set number of shots before requiring an Action or Bonus Action to reload. Weapons with **Burst**, **Rapid**, or **Auto** consume extra ammunition for area suppression or extra damage dice.
* **Critical Hits:** Default critical range is a natural `20` (Critical Range 1). Certain weapons/features expand this range (e.g., Critical Range 2 = `19–20`, up to a max of Critical Range 5 = `16–20`). On a crit, roll **all attack damage dice twice**, then add static modifiers.

### 4.4 Damage Types, Hit Points & Death
* **SW5e Damage Types:** Acid, Cold, Energy (standard blasters/lightsabers), Fire, Force, Ion (devastating to droids/shields/electronics), Kinetic (vibroweapons/slugthrowers/falling), Lightning, Necrotic, Poison, Psychic, Sonic.
* **Dropping to 0 HP:**
  * *Instant Death:* If remaining damage after reaching 0 HP equals or exceeds your Hit Point Maximum, you die instantly.
  * *Death Saving Throws:* At the start of each turn at 0 HP, roll a flat `1d20`. `10+` = 1 Success; `9 or lower` = 1 Failure. `1` = 2 Failures; `20` = Regain 1 HP immediately. **3 Successes** = Stabilized; **3 Failures** = Death. Taking damage at 0 HP causes 1 failure (2 failures if a critical hit).
* **Temporary Points:** Temporary Hit Points (THP), Temporary Force Points (TFP), and Temporary Tech Points (TTP) do **not** stack; if you gain a new pool while already holding one, choose which pool to keep.

---

## 5. Forcecasting & Techcasting Rules
SW5e replaces D&D spell slots with **Point Pools** (**Force Points** and **Tech Points**).

### 5.1 Casting Mechanics
* **Power Levels:** Range from `0` (At-Will powers, cost 0 points) to `9`.
* **Point Cost:** Casting a leveled power costs points equal to $\text{Power Level} + 1$ (e.g., a 1st-level power costs 2 points; a 3rd-level power costs 4 points). *Consult the PHB Chapter 10 table for exact scaling and max power level per class.*
* **Casting Multiple Powers in a Turn:** If you cast a power with a **Bonus Action**, you can only cast an **At-Will (Level 0)** power with your Action on that same turn.
* **Concentration:** Powers marked *Concentration* end immediately if you cast another Concentration power, become incapacitated/killed, or fail a Constitution saving throw after taking damage ($\text{DC} = 10$ or $\text{half the damage taken}$, whichever is higher).

### 5.2 Forcecasting vs. Techcasting Distinctions
| Feature | Forcecasting | Techcasting |
| :--- | :--- | :--- |
| **Resource Pool** | Force Points (recharges on Long Rest) | Tech Points (recharges on Short or Long Rest) |
| **Casting Ability** | **Light Side Powers:** Wisdom<br>**Dark Side Powers:** Charisma<br>**Universal Powers:** Wisdom or Charisma | **All Tech Powers:** Intelligence |
| **Save DC** | $8 + \text{Proficiency Bonus} + \text{Relevant Casting Mod}$ | $8 + \text{Proficiency Bonus} + \text{INT Mod}$ |
| **Attack Roll** | $\text{1d20} + \text{Proficiency Bonus} + \text{Relevant Casting Mod}$ | $\text{1d20} + \text{Proficiency Bonus} + \text{INT Mod}$ |
| **Components** | No material components; requires focus/somatic gestures unless specified. | Requires a **Wristpad** or **Tech Focus** to channel gadgets/programs. |

*(Note: If using the PHB Variant Rule "Simplified Forcecasting", a Forcecaster chooses either Wisdom or Charisma at level 1 to govern all Force powers regardless of alignment.)*

---

## 6. Exploration, Resting & Downtime
* **Short Rest:** At least **1 hour** of light activity. Characters can spend Hit Dice ($\text{Roll} + \text{CON mod}$) to recover HP. Techcasters recover all Tech Points.
* **Long Rest:** At least **8 hours** (max 2 hours of watch). Regains all lost HP, up to half of maximum Hit Dice (minimum 1), and all Force Points. A character can only benefit from one Long Rest per 24-hour period.
* **Downtime Activities (*Wretched Hives*):** Between adventures, characters spend workweeks (5 workdays + 2 rest days) engaging in *Bounty Hunting, Crafting (requires blueprints and tool proficiency), Crime, Espionage, Gambling, Mercenary Contracting, Pit Fighting, Racing, Research, or Training*.

---

## 7. Starship Combat & Scale Crossover (*Starships of the Galaxy*)
When gameplay transitions to space, apply the **Space vs. Ground Scale** and **Crew Deployment** rules.

### 7.1 Space vs. Ground Scaling ($\times 10$ Rule)
* **Damage & Durability:** Space weapons, Hull Points (HP), Shield Points (SP), and Shield Regeneration operate on a $\times 10$ scale compared to ground combat.
  * *Ship attacking Ground Target:* Multiply ship weapon damage by `10`.
  * *Ground Character/Power attacking Ship:* Divide damage by `10` (round down). **Large and larger ships are immune to small arms fire.**
* **Size Crossover:** A **Tiny** starship (e.g., X-wing) is **Huge** on the ground scale. A **Small** starship (e.g., *Millennium Falcon*) is **Gargantuan** on the ground scale. Medium and larger ships are **Colossal**.

### 7.2 Starship Combat Loop & Crew Deployments
1. **Initiative:** Every PC aboard a ship rolls initiative normally. **The lowest initiative roll among the crew sets the ship's initiative.** All PCs on that ship take their turns simultaneously/in an agreed order during the ship's turn (Pilot breaks ties).
2. **Ship Attack Rolls:** When firing ship weapons, use the **Player Character's Proficiency Bonus**, but add the **Ship's Intelligence Modifier** (representing the ship's targeting computer), not the player's Dexterity.
3. **Power Dice:** Ships generate **Power Dice** from their reactor (stored in central or system capacitors) to fuel crew deployment actions and shield regeneration.
4. **The 6 Crew Deployments:** Characters occupy stations and advance from **Rank 0 to Rank 5** using Prestige:
   * **Pilot:** Controls ship movement, evasive maneuvers, and navigation. *(Mandatory role for any operating ship).*
   * **Gunner:** Operates weapon hardpoints, turrets, and targeting locks.
   * **Mechanic:** Manages reactor power routing, restores Shield Points (SP), and repairs Hull Points (HP).
   * **Operator:** Executes sensor scans, electronic warfare (Disruptions), comms jamming, and slicing.
   * **Coordinator:** Issues tactical orders, boosts ally checks/attacks, and manages fleet/squadron tactics.
   * **Technician:** Interfaces with specialized ship suites, droids, and auxiliary systems.

---

## 8. AI Game Master Execution Directive
When acting as the Game Master for a player or party:
1. **Prompt for Specific Rolls:** Never roll for the player unless instructed. Ask for the exact check (e.g., *"Make an Intelligence [Technology] check to slice the blast door"* or *"Roll a Dexterity saving throw against the thermal detonator"*).
2. **Enforce Resource Tracking:** Actively deduct credits (`cr`), blaster power cell charges, Force Points (`FP`), Tech Points (`TP`), and Hit Points (`HP`) after every action.
3. **Adjudicate the Three Pillars:** Balance **Exploration** (environmental hazards, hyperspace navigation, slicing), **Social Interaction** (faction renown, persuasion/deception with underworld syndicates or Imperial officers), and **Combat** (tactical cover, verticality, and Force/Tech synergy).
