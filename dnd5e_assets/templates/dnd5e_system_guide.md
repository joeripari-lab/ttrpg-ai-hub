# Dungeons & Dragons 5th Edition (5e) — AI System Reference Guide

This document provides a structured, deterministic breakdown of Dungeons & Dragons 5th Edition (5e) mechanics. It is formatted specifically for ingestion by a local or cloud Large Language Model (LLM) acting as a Game Master (GM/DM), rules arbiter, or tactical combat engine.

---

## 1. Core Mechanics & Resolution Engine

All uncertain outcomes in D&D 5e are resolved using the **Core Mechanic**:
$$\text{Total} = \text{1d20} + \text{Ability Modifier} + \text{Proficiency Bonus (if applicable)} + \text{Situational Modifiers}$$

* **Success Condition:** If $\text{Total} \ge \text{Target Number}$ (DC for checks/saves, AC for attacks), the attempt succeeds. Ties always go to the roller (attacker/actor).
* **Natural 20 & Natural 1:**
  * **Attack Rolls:** A natural `20` is an automatic hit and a **Critical Hit** (roll all damage dice twice, then add modifiers). A natural `1` is an automatic miss regardless of modifiers.
  * **Ability Checks & Saving Throws:** By strict Rules As Written (RAW), natural `20`s and `1`s do **not** cause automatic success or failure on checks or saves (except Death Saving Throws).
* **Advantage and Disadvantage:**
  * **Advantage:** Roll `2d20`, use the **higher** result.
  * **Disadvantage:** Roll `2d20`, use the **lower** result.
  * **Cancellation Rule:** Advantage and Disadvantage do not stack. If a roll has *any* number of Advantage sources and *any* number of Disadvantage sources, they cancel out completely—roll `1d20` normally.

### Ability Scores & Modifiers
Every creature has six core attributes. Modifiers are calculated as:
$$\text{Modifier} = \lfloor (\text{Score} - 10) / 2 \rfloor$$

| Score | Modifier | Score | Modifier |
| :--- | :--- | :--- | :--- |
| 1 | -5 | 16–17 | +3 |
| 2–3 | -4 | 18–19 | +4 |
| 4–5 | -3 | 20–21 | +5 |
| 6–7 | -2 | 22–23 | +6 |
| 8–9 | -1 | 24–25 | +7 |
| 10–11 | +0 | 26–27 | +8 |
| 12–13 | +1 | 28–29 | +9 |
| 14–15 | +2 | 30 | +10 |

### Proficiency Bonus (PB)
Determined by total character level (or Challenge Rating for monsters):
* **Levels 1–4:** $+2$
* **Levels 5–8:** $+3$
* **Levels 9–12:** $+4$
* **Levels 13–16:** $+5$
* **Levels 17–20:** $+6$
* **Rule:** PB can only be added **once** to any single roll. Features like *Expertise* double the PB, while *Jack of All Trades* adds $\lfloor \text{PB} / 2 \rfloor$.

---

## 2. Skills & Ability Checks

Difficulty Classes (DCs) set by the DM:
* **5:** Very Easy | **10:** Easy | **15:** Medium | **20:** Hard | **25:** Very Hard | **30:** Nearly Impossible

### Skill-to-Ability Mapping
* **Strength (STR):** Athletics (climbing, jumping, swimming, grappling, shoving).
* **Dexterity (DEX):** Acrobatics (balance, flips), Sleight of Hand (pickpocketing, concealment), Stealth (hiding).
* **Constitution (CON):** *(No associated skills; used for raw endurance checks and Concentration).*
* **Intelligence (INT):** Arcana (magic lore), History (past events), Investigation (deduction, searching for clues), Nature (flora/fauna/weather), Religion (deities, rites).
* **Wisdom (WIS):** Animal Handling, Insight (reading intent/lies), Medicine (stabilizing, diagnosing), Perception (spotting hidden things), Survival (tracking, foraging, navigation).
* **Charisma (CHA):** Deception (lying), Intimidation (threats), Performance (entertaining), Persuasion (diplomacy, good-faith negotiation).

### Passive Checks
Used when the DM wants to determine success without alerting the player (e.g., noticing a hidden trap or sneaking creature):
$$\text{Passive Score} = 10 + \text{All normal modifiers to the check} + (5 \text{ if Advantage}) - (5 \text{ if Disadvantage})$$

---

## 3. Combat State Machine

Combat operates in strict **Rounds** (6 seconds of in-game time each). Every participant takes one **Turn** per round.

### Phase 1: Combat Initialization
1. **Determine Surprise:** Compare Stealth checks of hiding creatures against Passive Perception of targets. Any creature that fails to notice at least one threat is **Surprised** (cannot move or take actions on Turn 1, and cannot take Reactions until Turn 1 ends).
2. **Establish Positions:** Place combatants on grid/theater-of-the-mind (standard grid: $1 \text{ square} = 5 \text{ feet}$).
3. **Roll Initiative:** Every combatant makes a Dexterity check (`1d20 + DEX mod`). Order runs highest to lowest.

### Phase 2: Turn Structure
On a creature's turn, it receives the following resource budget:
* **Movement:** Up to its Speed in feet. Can be split before, between, and after actions.
  * *Difficult Terrain:* Costs $2\text{ ft}$ of movement per $1\text{ ft}$ moved.
  * *Standing from Prone:* Costs half of total Speed.
  * *Crawling/Climbing/Swimming:* Each $1\text{ ft}$ costs $2\text{ ft}$ of movement (unless the creature has a specific climb/swim speed).
* **1 Action:** The primary activity (see *Standard Actions* below).
* **1 Bonus Action:** Only available if a specific spell, class feature, or feat grants one.
* **1 Free Object Interaction:** Draw/sheathe one weapon, open an unlocked door, pick up a dropped item. (A second interaction requires the **Use an Object** Action).
* **1 Reaction (per Round):** Instant response to a trigger, usable on your turn or another creature's turn. Resets at the **start of your next turn**.

### Standard Actions
1. **Attack:** Make one melee or ranged weapon attack. (Classes with *Extra Attack* make multiple attacks with this single Action).
   * *Grapple (Special Melee Attack):* Replaces one attack. Target must be $\le 1$ size larger. Attacker's **Athletics** vs. Target's **Athletics or Acrobatics**. Success applies the *Grappled* condition.
   * *Shove (Special Melee Attack):* Replaces one attack. Target must be $\le 1$ size larger. Attacker's **Athletics** vs. Target's **Athletics or Acrobatics**. Success knocks target *Prone* or pushes it $5\text{ ft}$ away.
2. **Cast a Spell:** Cast a spell with a casting time of `1 Action`.
3. **Dash:** Gain extra movement equal to your current Speed for this turn.
4. **Disengage:** Your movement does not provoke Opportunity Attacks for the rest of the turn.
5. **Dodge:** Until the start of your next turn, any attack roll against you has **Disadvantage** (if you can see the attacker), and you make DEX saving throws with **Advantage**. (Lost if *Incapacitated* or Speed drops to `0`).
6. **Help:** Give an ally Advantage on their next ability check, OR give an ally Advantage on their next attack roll against a target within $5\text{ ft}$ of you.
7. **Hide:** Make a Dexterity (Stealth) check while heavily obscured or behind cover to become *Hidden* (unseen and unheard).
8. **Ready:** Declare a perceptible trigger and an Action (or movement) you will execute using your **Reaction** when that trigger occurs. *(Readying a spell requires Concentration and consumes the spell slot immediately, even if the trigger never happens).*
9. **Search:** Devote attention to finding something (Perception or Investigation check).
10. **Use an Object:** Interact with a second object or activate a non-magical item (e.g., drinking a potion, applying poison, throwing alchemist's fire).

### Attack Resolution & Cover
* **Melee Attacks:** Reach is typically $5\text{ ft}$. Uses **STR** (unless the weapon has the *Finesse* property, which allows **STR** or **DEX**).
* **Ranged Attacks:** Uses **DEX** (unless *Thrown* property on a melee weapon, which uses **STR**).
  * *Range:* Listed as `(Normal/Long)`. Attacking beyond Normal range up to Long range imposes **Disadvantage**.
  * *Ranged in Close Combat:* Making a ranged attack while within $5\text{ ft}$ of a hostile creature who can see you and isn't incapacitated imposes **Disadvantage**.
* **Two-Weapon Fighting:** When taking the Attack action with a *Light* melee weapon in one hand, you can use a **Bonus Action** to attack with a different *Light* melee weapon in the other hand. Do **not** add your ability modifier to the Bonus Action attack's damage (unless negative).
* **Opportunity Attack (Reaction):** Triggered when a hostile creature you can see moves **out** of your reach. Make one melee attack just before they leave.
* **Cover:**
  * **Half Cover:** $+2$ bonus to AC and DEX saving throws.
  * **Three-Quarters Cover:** $+5$ bonus to AC and DEX saving throws.
  * **Total Cover:** Cannot be targeted directly by an attack or spell.

---

## 4. Damage, Healing, & Dying

### Damage Types
Acid, Bludgeoning, Cold, Fire, Force, Lightning, Necrotic, Piercing, Poison, Psychic, Radiant, Slashing, Thunder.

### Resistance & Vulnerability
Applied **after** all other modifiers to damage:
* **Resistance:** Damage of that type is **halved** (rounded down).
* **Vulnerability:** Damage of that type is **doubled**.
* **Immunity:** Damage of that type is reduced to `0`.

### Hit Points (HP) & Temporary HP
* Damage subtracts from **Temporary HP** first; overflow carries into normal HP.
* Temporary HP **never stacks**; if you gain new Temp HP, choose to keep the old value or take the new value.
* Healing cannot raise HP above Maximum HP; healing a creature at `0 HP` restores HP and brings them back to consciousness.

### Dropping to 0 Hit Points
1. **Instant Death:** If remaining damage after reaching `0 HP` equals or exceeds the creature's **Maximum HP**, the creature dies instantly.
2. **Falling Unconscious:** Otherwise, the creature falls *Unconscious* and begins making **Death Saving Throws** at the start of each of its turns.
3. **Death Saving Throws:** Roll `1d20` (no modifiers):
   * **10 or higher:** 1 Success.
   * **9 or lower:** 1 Failure.
   * **Natural 20:** Regain `1 HP` and regain consciousness immediately.
   * **Natural 1:** Counts as **2 Failures**.
   * **Resolution:** 3 Successes = Stabilized (remains unconscious at `0 HP`, stops rolling). 3 Failures = Death.
4. **Taking Damage at 0 HP:** Any damage taken while at `0 HP` causes **1 automatic Death Save Failure** (or **2 Failures** if the damage is from a Critical Hit).

---

## 5. Spellcasting Rules

### Spell Slots & Casting
* Casting a spell of 1st level or higher expends a spell slot of that spell's level or higher.
* **Cantrips (0-level):** Cast at will without expending spell slots. Damage scales with total character level (levels 5, 11, 17).
* **Bonus Action Casting Rule (CRITICAL):** If you cast *any* spell using a **Bonus Action** (including a cantrip), you cannot cast any other spells during that same turn, **except for a cantrip with a casting time of 1 Action**.

### Components
* **Verbal (V):** Requires speaking aloud; impossible while gagged or in an area of *Silence*.
* **Somatic (S):** Requires at least one free hand for gestures.
* **Material (M):** Requires a Component Pouch or Spellcasting Focus. If a material component has a **specific gold cost** (e.g., *a diamond worth 300 gp*) or states it is **consumed**, the caster must physically possess that exact item.

### Spell Save DC & Attack Modifier
$$\text{Spell Save DC} = 8 + \text{Proficiency Bonus} + \text{Spellcasting Ability Modifier}$$
$$\text{Spell Attack Modifier} = \text{Proficiency Bonus} + \text{Spellcasting Ability Modifier}$$
*(Spellcasting Abilities: INT for Wizard/Artificer; WIS for Cleric/Druid/Ranger; CHA for Bard/Paladin/Sorcerer/Warlock).*

### Concentration
Some spells require **Concentration** to maintain. You can only concentrate on **one spell at a time**. Concentration ends immediately if:
1. You cast another spell that requires Concentration.
2. You take damage and fail a **Constitution Saving Throw**:
   $$\text{DC} = \max(10, \lfloor \text{Damage Taken} / 2 \rfloor)$$
   *(Rolled separately for each distinct source of damage).*
3. You become *Incapacitated* or die.

---

## 6. Resting & Recovery

* **Short Rest:** At least **1 hour** of light activity (eating, reading, tending wounds).
  * Characters may spend **Hit Dice** (up to their maximum pool equal to character level). For each Hit Die spent, roll the die + **CON modifier** and regain that many HP.
  * Recharges "Short Rest" features (e.g., Warlock Pact Magic, Fighter Action Surge, Monk Ki).
* **Long Rest:** At least **8 hours** (max 2 hours of light watch; at least 6 hours of sleep). A character can only benefit from **one Long Rest per 24-hour period** and must have at least `1 HP` at the start.
  * Regains all lost HP.
  * Regains spent Hit Dice up to **half** of total maximum Hit Dice (minimum of 1).
  * Regains all expended spell slots and "Long Rest" features.
  * Reduces **Exhaustion** by 1 level (if food and water were ingested).

---

## 7. Conditions Reference Matrix

| Condition | Mechanical Effects |
| :--- | :--- |
| **Blinded** | Automatically fails sight-based checks. Attack rolls against the creature have **Advantage**; the creature's attack rolls have **Disadvantage**. |
| **Charmed** | Cannot attack the charmer or target them with harmful abilities/effects. Charmer has **Advantage** on social ability checks against the creature. |
| **Deafened** | Cannot hear and automatically fails any ability check that requires hearing. |
| **Frightened** | **Disadvantage** on ability checks and attack rolls while the source of fear is within line of sight. Cannot willingly move closer to the source of fear. |
| **Grappled** | Speed becomes `0` and cannot benefit from bonuses to speed. Ends if grappler is *Incapacitated* or an effect moves the grappled creature out of reach. |
| **Incapacitated** | Cannot take **Actions** or **Reactions** (also breaks Concentration). |
| **Invisible** | Impossible to see without special senses (heavily obscured for hiding). Attack rolls against the creature have **Disadvantage**; the creature's attack rolls have **Advantage**. |
| **Paralyzed** | *Incapacitated*, cannot move or speak. Automatically fails **STR** and **DEX** saving throws. Attacks against have **Advantage**, and any hit from within $5\text{ ft}$ is an automatic **Critical Hit**. |
| **Petrified** | Turned to solid inanimate substance (weight $\times 10$). *Incapacitated*, unaware of surroundings. Attacks against have **Advantage**. Auto-fails STR/DEX saves. **Resistance** to all damage; immune to poison and disease. |
| **Poisoned** | **Disadvantage** on attack rolls and ability checks. |
| **Prone** | Only movement option is to crawl (unless standing up). **Disadvantage** on attack rolls. Attacks against have **Advantage** if attacker is within $5\text{ ft}$, otherwise **Disadvantage**. |
| **Restrained** | Speed becomes `0`. Attack rolls against have **Advantage**; creature's attack rolls have **Disadvantage**. **Disadvantage** on **DEX** saving throws. |
| **Stunned** | *Incapacitated*, cannot move, speaks only falteringly. Automatically fails **STR** and **DEX** saving throws. Attacks against have **Advantage**. |
| **Unconscious** | *Incapacitated*, cannot move or speak, unaware of surroundings. Drops whatever it is holding and falls *Prone*. Auto-fails **STR** and **DEX** saves. Attacks against have **Advantage**; any hit within $5\text{ ft}$ is a **Critical Hit**. |

### Exhaustion Levels (Cumulative)
1. **Level 1:** Disadvantage on ability checks.
2. **Level 2:** Speed halved.
3. **Level 3:** Disadvantage on attack rolls and saving throws.
4. **Level 4:** Hit point maximum halved.
5. **Level 5:** Speed reduced to `0`.
6. **Level 6:** Death.

---

## 8. AI Game Master Execution Directives

When acting as a D&D 5e engine or DM, follow this state-tracking loop:
1. **Validate Action Economy:** Ensure the actor has the required Action, Bonus Action, Reaction, Movement, or Spell Slot before resolving.
2. **Check Conditions & Modifiers:** Apply Advantage/Disadvantage, Cover, Concentration checks, and active Conditions before rolling dice.
3. **Enforce Bonus Action Spell Rule:** If a Bonus Action spell is cast, restrict any other spell on that turn to a `1 Action` cantrip.
4. **Resolve Damage Sequentially:** Subtract Temporary HP $\rightarrow$ Apply Resistance/Vulnerability $\rightarrow$ Subtract HP $\rightarrow$ Check `0 HP` / Instant Death / Concentration (`DC = max(10, floor(damage/2))`).
5. **Output Concisely:** State the roll formula, target DC/AC, outcome, and updated HP/Condition state clearly.
