CREATE TABLE IF NOT EXISTS warehouse_cycle_counts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    lot_id INT NOT NULL,
    count_ref VARCHAR(60) NOT NULL UNIQUE,
    system_units INT UNSIGNED NOT NULL,
    counted_units INT UNSIGNED NOT NULL,
    discrepancy_reason VARCHAR(300) NOT NULL,
    counted_by INT NOT NULL,
    counted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    state ENUM('pending','posted','rejected') NOT NULL DEFAULT 'pending',
    reviewer_note VARCHAR(300) NULL,
    reviewed_by INT NULL,
    reviewed_at TIMESTAMP NULL,
    KEY ix_count_review (lot_id, state),
    FOREIGN KEY (lot_id) REFERENCES warehouse_lots(id),
    FOREIGN KEY (counted_by) REFERENCES users(id),
    FOREIGN KEY (reviewed_by) REFERENCES users(id)
);
