DROP DATABASE IF EXISTS music_app;
CREATE DATABASE music_app;
USE music_app;

-- USERS
CREATE TABLE users(
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    email_id VARCHAR(100) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    password VARCHAR(60) NOT NULL,
    sign_up_date DATE NOT NULL,
    user_role ENUM('user','artist') NOT NULL DEFAULT 'user',
    wallet_balance DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    subscription_type ENUM('free','premium','monthly','annual') NULL,
    subscription_start DATE NULL,
    subscription_end DATE NULL,
    CONSTRAINT chk_artist_subscription_fields
      CHECK (
        (user_role = 'artist' AND subscription_type IS NULL AND subscription_start IS NULL AND subscription_end IS NULL)
        OR
        (user_role <> 'artist')
      )
) ENGINE=InnoDB;

-- PLAYLIST
CREATE TABLE playlist(
    playlist_id INT AUTO_INCREMENT PRIMARY KEY,
    playlist_name TEXT NOT NULL,
    created_date DATE NOT NULL,
    user_id INT,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
) ENGINE=InnoDB;

-- SONGS
CREATE TABLE songs(
    song_id INT AUTO_INCREMENT PRIMARY KEY,
    num_plays INT DEFAULT 0,
    num_likes INT DEFAULT 0,
    num_downloads INT DEFAULT 0,
    song_title TEXT NOT NULL,
    duration INT NOT NULL,
    popularity_score DOUBLE DEFAULT 0,
    release_date DATETIME
) ENGINE=InnoDB;

-- ARTIST
CREATE TABLE artist(
    artist_id INT AUTO_INCREMENT PRIMARY KEY,
    artist_name VARCHAR(100) NOT NULL,
    nationality VARCHAR(100),
    num_followers INT DEFAULT 0,
    monetization_status ENUM('monetized','notmonetized') NOT NULL DEFAULT 'monetized'
) ENGINE=InnoDB;

-- GENRE
CREATE TABLE genre(
    genre_id INT AUTO_INCREMENT PRIMARY KEY,
    genre_name VARCHAR(100) NOT NULL
) ENGINE=InnoDB;

-- MAKE_SONG (Many-to-Many)
CREATE TABLE make_song(
    song_id INT,
    artist_id INT,
    PRIMARY KEY (song_id, artist_id),
    FOREIGN KEY (song_id) REFERENCES songs(song_id),
    FOREIGN KEY (artist_id) REFERENCES artist(artist_id)
) ENGINE=InnoDB;
-- Like Song

CREATE TABLE user_likes_song (
    user_id INT,
    song_id INT,
    PRIMARY KEY (user_id, song_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (song_id) REFERENCES songs(song_id)
);

-- CATEGORIZE SONG
CREATE TABLE categorize_song(
    song_id INT,
    genre_id INT,
    PRIMARY KEY (song_id, genre_id),
    FOREIGN KEY (song_id) REFERENCES songs(song_id),
    FOREIGN KEY (genre_id) REFERENCES genre(genre_id)
) ENGINE=InnoDB;

-- PLAYLIST SONGS
CREATE TABLE playlist_songs(
    playlist_id INT,
    song_id INT,
    PRIMARY KEY (playlist_id, song_id),
    FOREIGN KEY (playlist_id) REFERENCES playlist(playlist_id),
    FOREIGN KEY (song_id) REFERENCES songs(song_id)
) ENGINE=InnoDB;

CREATE TABLE song_sales(
    sale_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    song_id INT NOT NULL,
    sale_amount DECIMAL(10,2) NOT NULL,
    sold_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_song_sales_user_song (user_id, song_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (song_id) REFERENCES songs(song_id)
) ENGINE=InnoDB;

CREATE TABLE artist_transactions(
    transaction_id INT AUTO_INCREMENT PRIMARY KEY,
    artist_id INT NOT NULL,
    song_id INT,
    sale_id INT,
    transaction_type ENUM('sale_credit','manual_adjustment') NOT NULL DEFAULT 'sale_credit',
    amount DECIMAL(10,2) NOT NULL,
    notes VARCHAR(255),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (artist_id) REFERENCES artist(artist_id),
    FOREIGN KEY (song_id) REFERENCES songs(song_id),
    FOREIGN KEY (sale_id) REFERENCES song_sales(sale_id)
) ENGINE=InnoDB;

-- USER HISTORY
CREATE TABLE user_history(
    user_id INT,
    song_id INT,
    listening_time TIMESTAMP,
    listening_count INT DEFAULT 1,
    PRIMARY KEY (user_id, song_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (song_id) REFERENCES songs(song_id)
) ENGINE=InnoDB;

-- USER FOLLOWS
CREATE TABLE user_follows_artist(
    user_id INT,
    artist_id INT,
    PRIMARY KEY (user_id, artist_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (artist_id) REFERENCES artist(artist_id)
) ENGINE=InnoDB;

-- USER DOWNLOADS (For Premium Users)
CREATE TABLE user_downloads(
    download_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    song_id INT NOT NULL,
    downloaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_downloads_user_song (user_id, song_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (song_id) REFERENCES songs(song_id)
) ENGINE=InnoDB;


-- INDEXES
CREATE INDEX idx_songs_popularity ON songs(popularity_score);
CREATE INDEX idx_songs_num_plays ON songs(num_plays);
CREATE INDEX idx_artist_followers ON artist(num_followers);
CREATE INDEX idx_playlist_user ON playlist(user_id);
CREATE INDEX idx_user_history_time ON user_history(listening_time);
CREATE INDEX idx_song_sales_song ON song_sales(song_id);
CREATE INDEX idx_artist_transactions_artist ON artist_transactions(artist_id);
CREATE INDEX idx_artist_transactions_time ON artist_transactions(created_at);

DELIMITER $$

CREATE TRIGGER before_users_insert
BEFORE INSERT ON users
FOR EACH ROW
BEGIN
    IF NEW.user_role = 'artist' THEN
        SET NEW.subscription_type = NULL;
        SET NEW.subscription_start = NULL;
        SET NEW.subscription_end = NULL;
    ELSE
        IF NEW.subscription_type IS NULL THEN
            SET NEW.subscription_type = 'free';
        END IF;
    END IF;
END$$

DELIMITER ;

DELIMITER $$

CREATE TRIGGER before_users_update
BEFORE UPDATE ON users
FOR EACH ROW
BEGIN
    IF NEW.user_role = 'artist' THEN
        SET NEW.subscription_type = NULL;
        SET NEW.subscription_start = NULL;
        SET NEW.subscription_end = NULL;
    ELSE
        IF NEW.subscription_type IS NULL THEN
            SET NEW.subscription_type = 'free';
        END IF;
    END IF;
END$$

DELIMITER ;

DELIMITER $$

CREATE TRIGGER after_song_sale_insert
AFTER INSERT ON song_sales
FOR EACH ROW
BEGIN
    UPDATE songs
    SET num_downloads = num_downloads + 1
    WHERE song_id = NEW.song_id;
END$$

DELIMITER ;

DELIMITER $$

CREATE TRIGGER after_history_insert
AFTER INSERT ON user_history
FOR EACH ROW
BEGIN
    UPDATE songs
    SET num_plays = num_plays + 1
    WHERE song_id = NEW.song_id;
END$$

DELIMITER ;

DELIMITER $$

CREATE TRIGGER after_history_update
AFTER UPDATE ON user_history
FOR EACH ROW
BEGIN
    IF NEW.listening_count > OLD.listening_count THEN
        UPDATE songs
        SET num_plays = num_plays + 1
        WHERE song_id = NEW.song_id;
    END IF;
END$$

DELIMITER ;

DELIMITER $$

CREATE TRIGGER after_follow_insert
AFTER INSERT ON user_follows_artist
FOR EACH ROW
BEGIN
    UPDATE artist
    SET num_followers = num_followers + 1
    WHERE artist_id = NEW.artist_id;
END$$

DELIMITER ;

DELIMITER $$

CREATE TRIGGER after_follow_delete
AFTER DELETE ON user_follows_artist
FOR EACH ROW
BEGIN
    UPDATE artist
    SET num_followers = num_followers - 1
    WHERE artist_id = OLD.artist_id;
END$$

DELIMITER ;

-- passwords of u1 = pw1, u2=pw2,....artist1=pw6
INSERT INTO users (email_id, name, password, sign_up_date, user_role, subscription_type, subscription_start, subscription_end) VALUES
('u1@gmail.com', 'Alice', '$2b$12$5NmCLuJZ0Q.XWlvgrUI6keax37IqlGCRitmwxuMR/stsm9Uv9GT.q', '2024-01-10', 'user', 'free', NULL, NULL),
('u2@gmail.com', 'Bob', '$2b$12$XR6x46eCOuuVqlRfJ1Xse.IeQuQXlV3e8f/4U5ceoz2ycvnQk1sE2', '2024-01-15', 'user', 'premium', '2024-01-15', '2025-01-15'),
('u3@gmail.com', 'Charlie', '$2b$12$Mc1E0pKy7Tzr8wn7VuU.dedorVyHbbn7WReI/bVrncd5T2cm9X64G', '2024-02-01', 'user', 'free', NULL, NULL),
('u4@gmail.com', 'Daisy', '$2b$12$ndXkqHIF.8CvKxpz2z2hdetO9.CI1aivuGHQWCteEjidj3GmOthke', '2024-02-10', 'user', 'premium', '2024-02-10', '2025-02-10'),
('artist1@gmail.com', 'Artist One', '$2b$12$CmWYHbICWa8BeHOb817/bO5V4EuKMZ28Vay8S.fSJr7bGcSyItZFG', '2024-01-20', 'artist', NULL, NULL, NULL);

UPDATE users SET wallet_balance = 120.00 WHERE user_id IN (1, 2, 3, 4, 5, 6);

INSERT INTO artist (artist_name, nationality, num_followers, monetization_status) VALUES
('Arijit Singh', 'India', 5000000, 'monetized'),
('Taylor Swift', 'USA', 12000000, 'monetized'),
('AP Dhillon', 'India', 2000000, 'monetized'),
('Indie Band X', 'India', 50000, 'notmonetized'),
('Coldplay', 'UK', 9000000, 'monetized'),
('Artist One', 'USA', 1000, 'notmonetized');

INSERT INTO genre (genre_name) VALUES
('Pop'),
('Rock'),
('Romantic'),
('Indie'),
('Hip-Hop');

INSERT INTO songs (song_title, duration, release_date, num_plays, num_likes, popularity_score) VALUES
('Neon Nights', 205, '2022-05-01', 87000, 4300, 82.1),
('Desert Rain', 233, '2021-08-11', 54000, 2100, 74.2),
('City Lights', 198, '2023-02-14', 132000, 7200, 88.4),
('Broken Radio', 176, '2020-09-09', 22000, 900, 61.3),
('Ocean Drive', 244, '2024-01-20', 45000, 2600, 77.5),
('Midnight Run', 201, '2023-07-07', 91000, 4800, 83.7),
('Parallel Hearts', 215, '2022-03-03', 67000, 3500, 79.6),
('Echo Chamber', 189, '2021-12-12', 38000, 1600, 69.9),
('Golden Hour', 226, '2024-02-02', 120000, 8000, 90.2),
('Indie Dreams', 210, '2020-04-18', 31000, 1400, 66.8),
('Pulse Wave', 174, '2023-05-22', 76000, 3900, 81.0),
('Sky Runner', 208, '2022-06-30', 55000, 2700, 75.9),
('Fire Within', 230, '2021-01-15', 47000, 2500, 73.3),
('Soft Horizon', 260, '2024-03-01', 29000, 1200, 64.1),
('Urban Echo', 199, '2023-10-10', 61000, 3000, 78.8),
('Dreamcatcher', 242, '2022-11-11', 72000, 4100, 84.0),
('Night Signals', 187, '2020-02-20', 26000, 1000, 62.0),
('Silver Lines', 214, '2023-04-04', 99000, 5200, 86.5),
('Deep Focus', 300, '2021-06-06', 15000, 600, 58.2),
('Chill Circuit', 268, '2024-01-01', 34000, 1700, 70.4),
('Electric Love', 207, '2022-09-09', 111000, 6400, 89.1),
('Gravity Fall', 219, '2023-03-18', 69000, 3600, 80.3),
('Indie Pulse', 193, '2021-07-07', 28000, 1300, 65.9),
('Street Story', 222, '2020-10-10', 36000, 1800, 71.2),
('Sunset Ride', 205, '2024-02-18', 41000, 2200, 76.0),
('Moon Echo', 238, '2022-12-24', 53000, 2600, 74.5),
('Fusion Beat', 182, '2023-06-16', 88000, 4900, 83.0),
('LoFi Walk', 275, '2021-05-05', 21000, 900, 60.8),
('Rain Letters', 246, '2022-08-08', 47000, 2400, 73.9),
('Pop Riot', 199, '2024-01-30', 125000, 9100, 91.7),
('Artist One Anthem', 212, NOW(), 0, 0, 0);

INSERT INTO make_song (song_id, artist_id) VALUES
(1, 1),
(2, 2),
(3, 4),
(4, 5),
(5, 3);

INSERT INTO categorize_song (song_id, genre_id) VALUES
(1, 3),
(2, 1),
(3, 4),
(4, 2),
(5, 5);

INSERT INTO playlist (playlist_name, created_date, user_id) VALUES
('Chill Vibes', '2024-03-01', 1),
('Workout Hits', '2024-03-02', 2),
('Romantic Mix', '2024-03-05', 3),
('Indie Loop', '2024-03-07', 4),
('Top Charts', '2024-03-10', 2);

INSERT INTO playlist_songs (playlist_id, song_id) VALUES
(1, 1),
(1, 3),
(2, 4),
(3, 1),
(5, 2);

-- SONG SALES & TRANSACTIONS
INSERT INTO song_sales (user_id, song_id, sale_amount, sold_at) VALUES
(2, 1, 29.00, NOW()),
(2, 2, 29.00, NOW()),
(4, 4, 29.00, NOW()),
(3, 3, 29.00, NOW()),
(1, 5, 29.00, NOW());

-- Artist transaction records (revenue split from song sales)
INSERT INTO artist_transactions (artist_id, song_id, sale_id, transaction_type, amount, notes) VALUES
(1, 1, 1, 'sale_credit', 29.00, 'User 2 purchased Song 1'),
(2, 2, 2, 'sale_credit', 29.00, 'User 2 purchased Song 2'),
(5, 4, 3, 'sale_credit', 29.00, 'User 4 purchased Song 4'),
(4, 3, 4, 'sale_credit', 29.00, 'User 3 purchased Song 3'),
(3, 5, 5, 'sale_credit', 29.00, 'User 1 purchased Song 5');

INSERT INTO user_history (user_id, song_id, listening_time, listening_count) VALUES
(1, 1, '2024-03-10 10:30:00', 5),
(1, 3, '2024-03-11 21:00:00', 2),
(2, 2, '2024-03-12 08:00:00', 10),
(3, 5, '2024-03-12 19:00:00', 1),
(4, 4, '2024-03-13 22:15:00', 7);

INSERT INTO user_follows_artist (user_id, artist_id) VALUES
(1, 1),
(1, 2),
(2, 2),
(3, 3),
(4, 5);




INSERT INTO make_song VALUES
(6,1),(7,1),(8,1),
(9,2),(10,2),(11,2),
(12,3),(13,3),(14,3),
(15,4),(16,4),(17,4),
(18,5),(19,5),(20,5),
(21,1),(21,2),
(22,2),(22,5),
(23,3),(23,4),
(24,1),(24,3),
(25,2),(25,4),
(26,5),(26,3),
(27,4),(27,1),
(28,2),(28,3),
(29,1),(29,5),
(30,3),(30,5),
(31,6);


INSERT INTO categorize_song VALUES
(6,1),(6,3),
(7,3),
(8,4),
(9,1),(9,2),
(10,4),
(11,1),
(12,5),
(13,2),
(14,3),(14,1),
(15,4),
(16,5),(16,1),
(17,2),
(18,2),(18,1),
(19,1),
(20,1),(20,5),
(21,3),(21,1),
(22,2),
(23,4),(23,3),
(24,4),
(25,5),
(26,2),
(27,4),
(28,1),
(29,5),(29,3),
(30,4),
(31,1);



INSERT INTO playlist (playlist_name, created_date, user_id) VALUES
('Late Night Coding','2024-03-15',1),
('Road Trip','2024-03-16',2),
('Focus Mode','2024-03-17',4),
('Party Mix','2024-03-18',2);


INSERT INTO playlist_songs VALUES
(6,6),(6,10),(6,30),
(7,18),(7,21),(7,29),
(8,23),(8,24),(8,15),
(9,25),(9,30),(9,20),
(1,21),
(2,21),
(3,9),
(5,9);


INSERT INTO song_sales (user_id, song_id, sale_amount, sold_at) VALUES
(2,6,29.00,NOW()),(2,7,29.00,NOW()),(2,21,29.00,NOW()),
(4,9,29.00,NOW()),(4,10,29.00,NOW()),(4,22,29.00,NOW()),
(5,18,29.00,NOW()),(5,19,29.00,NOW()),(5,23,29.00,NOW()),
(2,31,29.00,NOW());


INSERT INTO user_history VALUES
(1,6,'2024-03-14 10:00:00',3),
(1,21,'2024-03-14 22:00:00',6),
(2,9,'2024-03-15 08:30:00',12),
(2,18,'2024-03-15 19:00:00',4),
(3,10,'2024-03-16 21:15:00',2),
(3,24,'2024-03-16 23:00:00',5),
(4,22,'2024-03-17 06:45:00',9),
(4,25,'2024-03-17 18:20:00',3),
(5,29,'2024-03-18 20:10:00',7),
(5,17,'2024-03-18 21:55:00',11);


INSERT INTO user_follows_artist VALUES
(2,1),
(2,5),
(3,2),
(4,1),
(5,2),
(5,5);

INSERT INTO artist_transactions (artist_id, song_id, sale_id, transaction_type, amount, notes, created_at)
SELECT
    ms.artist_id,
    ss.song_id,
    ss.sale_id,
    'sale_credit',
    ROUND(ss.sale_amount / artist_counts.artist_count, 2) AS amount,
    CONCAT('Seed revenue from sale #', ss.sale_id),
    ss.sold_at
FROM song_sales ss
JOIN make_song ms ON ms.song_id = ss.song_id
JOIN (
    SELECT song_id, COUNT(*) AS artist_count
    FROM make_song
    GROUP BY song_id
) artist_counts ON artist_counts.song_id = ss.song_id;

-- STORED PROCEDURE: Check and update expired subscriptions
DELIMITER //
CREATE PROCEDURE check_and_update_subscription(IN p_user_id INT)
BEGIN
    -- Check if user has an expired subscription and downgrade to free
    IF EXISTS (
        SELECT 1 FROM users
        WHERE user_id = p_user_id
        AND user_role <> 'artist'
        AND subscription_type IS NOT NULL
        AND subscription_type <> 'free'
        AND subscription_end IS NOT NULL
        AND subscription_end < CURDATE()
    ) THEN
        UPDATE users
        SET subscription_type = 'free',
            subscription_start = NULL,
            subscription_end = NULL
        WHERE user_id = p_user_id;
    END IF;
END //
DELIMITER ;