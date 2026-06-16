-- MySQL schema for the attached history item

CREATE TABLE accounts_niveau (
  id CHAR(32) PRIMARY KEY,
  code VARCHAR(50) NOT NULL UNIQUE,
  nom VARCHAR(120) NOT NULL UNIQUE,
  ordre INT UNSIGNED NOT NULL DEFAULT 0,
  actif BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE accounts_classe (
  id CHAR(32) PRIMARY KEY,
  niveau_id CHAR(32) NOT NULL,
  code VARCHAR(50) NOT NULL,
  nom VARCHAR(120) NOT NULL,
  annee_scolaire VARCHAR(20) NOT NULL,
  capacite INT UNSIGNED NOT NULL DEFAULT 0,
  actif BOOLEAN NOT NULL DEFAULT TRUE,
  CONSTRAINT uniq_classe_par_niveau_code_annee UNIQUE (niveau_id, code, annee_scolaire),
  CONSTRAINT fk_classe_niveau FOREIGN KEY (niveau_id) REFERENCES accounts_niveau(id) ON DELETE RESTRICT
);

CREATE TABLE accounts_utilisateur (
  id CHAR(32) PRIMARY KEY,
  email VARCHAR(255) NOT NULL UNIQUE,
  role VARCHAR(20) NOT NULL DEFAULT 'ELEVE',
  statut_compte VARCHAR(20) NOT NULL DEFAULT 'PENDING',
  classe_id CHAR(32) NULL,
  date_creation DATETIME NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT FALSE,
  is_staff BOOLEAN NOT NULL DEFAULT FALSE,
  is_formateur BOOLEAN NOT NULL DEFAULT FALSE,
  password VARCHAR(128) NOT NULL,
  last_login DATETIME NULL,
  is_superuser BOOLEAN NOT NULL DEFAULT FALSE,
  CONSTRAINT fk_utilisateur_classe FOREIGN KEY (classe_id) REFERENCES accounts_classe(id) ON DELETE SET NULL
);

CREATE TABLE apprentissage_cours (
  id CHAR(32) PRIMARY KEY,
  titre VARCHAR(255) NOT NULL,
  description TEXT NOT NULL,
  niveau_id CHAR(32) NOT NULL,
  resume TEXT NULL,
  date_creation DATETIME NOT NULL,
  date_modification DATETIME NOT NULL,
  actif BOOLEAN NOT NULL DEFAULT TRUE,
  createur_id CHAR(32) NULL,
  CONSTRAINT fk_cours_niveau FOREIGN KEY (niveau_id) REFERENCES accounts_niveau(id) ON DELETE CASCADE,
  CONSTRAINT fk_cours_createur FOREIGN KEY (createur_id) REFERENCES accounts_utilisateur(id) ON DELETE SET NULL
);

CREATE TABLE apprentissage_chapitre (
  id CHAR(32) PRIMARY KEY,
  cours_id CHAR(32) NOT NULL,
  titre VARCHAR(255) NOT NULL,
  description TEXT NULL,
  ordre INT UNSIGNED NOT NULL,
  url_video VARCHAR(200) NULL,
  date_creation DATETIME NOT NULL,
  actif BOOLEAN NOT NULL DEFAULT TRUE,
  CONSTRAINT uniq_chapitre_cours_ordre UNIQUE (cours_id, ordre),
  CONSTRAINT fk_chapitre_cours FOREIGN KEY (cours_id) REFERENCES apprentissage_cours(id) ON DELETE CASCADE
);

CREATE TABLE apprentissage_document (
  id CHAR(32) PRIMARY KEY,
  chapitre_id CHAR(32) NOT NULL,
  titre VARCHAR(255) NOT NULL,
  type_document VARCHAR(20) NOT NULL,
  fichier_pdf VARCHAR(100) NOT NULL,
  description TEXT NULL,
  contenu_extrait TEXT NULL,
  ordre INT UNSIGNED NOT NULL DEFAULT 0,
  date_creation DATETIME NOT NULL,
  date_modification DATETIME NOT NULL,
  actif BOOLEAN NOT NULL DEFAULT TRUE,
  CONSTRAINT fk_document_chapitre FOREIGN KEY (chapitre_id) REFERENCES apprentissage_chapitre(id) ON DELETE CASCADE
);

CREATE TABLE apprentissage_progression (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  etudiant_id CHAR(32) NOT NULL,
  cours_id CHAR(32) NOT NULL,
  date_derniere_consultation DATETIME NOT NULL,
  date_creation DATETIME NOT NULL,
  CONSTRAINT uniq_progression_etudiant_cours UNIQUE (etudiant_id, cours_id),
  CONSTRAINT fk_progression_etudiant FOREIGN KEY (etudiant_id) REFERENCES accounts_utilisateur(id) ON DELETE CASCADE,
  CONSTRAINT fk_progression_cours FOREIGN KEY (cours_id) REFERENCES apprentissage_cours(id) ON DELETE CASCADE
);

CREATE TABLE apprentissage_progression_chapitres_valides (
  progression_id BIGINT NOT NULL,
  chapitre_id CHAR(32) NOT NULL,
  PRIMARY KEY (progression_id, chapitre_id),
  CONSTRAINT fk_pc_progression FOREIGN KEY (progression_id) REFERENCES apprentissage_progression(id) ON DELETE CASCADE,
  CONSTRAINT fk_pc_chapitre FOREIGN KEY (chapitre_id) REFERENCES apprentissage_chapitre(id) ON DELETE CASCADE
);

CREATE TABLE apprentissage_chapitrevisite (
  id CHAR(32) PRIMARY KEY,
  etudiant_id CHAR(32) NOT NULL,
  chapitre_id CHAR(32) NOT NULL,
  date_visite DATETIME NOT NULL,
  CONSTRAINT uniq_chapitrevisite_etudiant_chapitre UNIQUE (etudiant_id, chapitre_id),
  CONSTRAINT fk_cv_etudiant FOREIGN KEY (etudiant_id) REFERENCES accounts_utilisateur(id) ON DELETE CASCADE,
  CONSTRAINT fk_cv_chapitre FOREIGN KEY (chapitre_id) REFERENCES apprentissage_chapitre(id) ON DELETE CASCADE
);

CREATE TABLE apprentissage_chapitrecomplete (
  id CHAR(32) PRIMARY KEY,
  etudiant_id CHAR(32) NOT NULL,
  chapitre_id CHAR(32) NOT NULL,
  date_completion DATETIME NOT NULL,
  CONSTRAINT uniq_chapitrecomplete_etudiant_chapitre UNIQUE (etudiant_id, chapitre_id),
  CONSTRAINT fk_cc_etudiant FOREIGN KEY (etudiant_id) REFERENCES accounts_utilisateur(id) ON DELETE CASCADE,
  CONSTRAINT fk_cc_chapitre FOREIGN KEY (chapitre_id) REFERENCES apprentissage_chapitre(id) ON DELETE CASCADE
);

CREATE TABLE logistics_equipment (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  nom VARCHAR(255) NOT NULL,
  numero_serie VARCHAR(255) NOT NULL UNIQUE,
  etat VARCHAR(20) NOT NULL DEFAULT 'DISPONIBLE',
  note TEXT NULL
);

CREATE TABLE logistics_workshop (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  titre VARCHAR(255) NOT NULL,
  date_debut DATETIME NOT NULL,
  date_fin DATETIME NOT NULL,
  salle VARCHAR(120) NOT NULL,
  tuteur_id CHAR(32) NOT NULL,
  niveau_cible VARCHAR(100) NOT NULL,
  CONSTRAINT fk_workshop_tuteur FOREIGN KEY (tuteur_id) REFERENCES accounts_utilisateur(id) ON DELETE RESTRICT
);

CREATE TABLE logistics_ticket (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  titre VARCHAR(255) NOT NULL,
  description TEXT NOT NULL,
  equipement_id BIGINT NULL,
  atelier_id BIGINT NULL,
  ouvert_par_id CHAR(32) NOT NULL,
  statut VARCHAR(20) NOT NULL DEFAULT 'OUVERT',
  CONSTRAINT fk_ticket_equipement FOREIGN KEY (equipement_id) REFERENCES logistics_equipment(id) ON DELETE SET NULL,
  CONSTRAINT fk_ticket_atelier FOREIGN KEY (atelier_id) REFERENCES logistics_workshop(id) ON DELETE SET NULL,
  CONSTRAINT fk_ticket_ouvert_par FOREIGN KEY (ouvert_par_id) REFERENCES accounts_utilisateur(id) ON DELETE RESTRICT
);

CREATE TABLE logistics_demandemateriel (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  formateur_id CHAR(32) NOT NULL,
  equipement_id BIGINT NOT NULL,
  atelier_cible_id BIGINT NULL,
  quantite INT UNSIGNED NOT NULL,
  statut VARCHAR(20) NOT NULL DEFAULT 'PENDING',
  date_creation DATETIME NOT NULL,
  date_mise_a_jour DATETIME NOT NULL,
  CONSTRAINT fk_dm_formateur FOREIGN KEY (formateur_id) REFERENCES accounts_utilisateur(id) ON DELETE CASCADE,
  CONSTRAINT fk_dm_equipement FOREIGN KEY (equipement_id) REFERENCES logistics_equipment(id) ON DELETE RESTRICT,
  CONSTRAINT fk_dm_atelier FOREIGN KEY (atelier_cible_id) REFERENCES logistics_workshop(id) ON DELETE SET NULL
);
