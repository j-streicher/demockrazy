-- Baseline-Schema, erzeugt aus 'makemigrations' auf Basis-Commit 3074dbb
-- Django 4.2.9 / Python 3.11.6 (nixpkgs mayflower/mf-stable, Lock 2024-02-07)
-- Zweck: Referenz zur Verifikation der eingecheckten 0001_initial (Plan 0.4 / 2.1)

CREATE TABLE "vote_choice" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "choice_text" text NOT NULL, "votes" integer NOT NULL, "poll_id" integer NOT NULL REFERENCES "vote_poll" ("id") DEFERRABLE INITIALLY DEFERRED);
CREATE INDEX "vote_choice_poll_id_8401e113" ON "vote_choice" ("poll_id");
CREATE TABLE "vote_poll" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "title" varchar(200) NOT NULL, "type" varchar(20) NOT NULL, "num_tokens" integer NULL, "question_text" text NOT NULL, "pub_date" datetime NOT NULL, "creator_token" varchar(512) NOT NULL, "identifier" varchar(64) NOT NULL, "is_active" bool NOT NULL);
CREATE TABLE "vote_token" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "token_string" varchar(128) NOT NULL, "poll_id" integer NOT NULL REFERENCES "vote_poll" ("id") DEFERRABLE INITIALLY DEFERRED);
CREATE INDEX "vote_token_poll_id_e1049aa3" ON "vote_token" ("poll_id");
