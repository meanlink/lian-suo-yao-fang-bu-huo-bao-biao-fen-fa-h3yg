CREATE TABLE IF NOT EXISTS warehouse_recalls (
    id INT AUTO_INCREMENT PRIMARY KEY,
    lot_id INT NOT NULL UNIQUE,
    notice_ref VARCHAR(70) NOT NULL UNIQUE,
    reason VARCHAR(300) NOT NULL,
    opened_by INT NOT NULL,
    opened_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMP NULL,
    FOREIGN KEY (lot_id) REFERENCES warehouse_lots(id),
    FOREIGN KEY (opened_by) REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS warehouse_recall_actions (
    recall_id INT NOT NULL,
    picklist_id INT NOT NULL,
    status_at_notice ENUM('reserved','packed','dispatched') NOT NULL,
    exposed_units INT UNSIGNED NOT NULL,
    outlet_ref VARCHAR(100) NULL,
    isolated_units INT UNSIGNED NULL,
    handled_by INT NULL,
    handled_at TIMESTAMP NULL,
    PRIMARY KEY (recall_id, picklist_id),
    FOREIGN KEY (recall_id) REFERENCES warehouse_recalls(id),
    FOREIGN KEY (picklist_id) REFERENCES warehouse_picklists(id),
    FOREIGN KEY (handled_by) REFERENCES users(id)
);
