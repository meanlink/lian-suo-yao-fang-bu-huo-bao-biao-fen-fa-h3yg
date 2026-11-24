CREATE TABLE IF NOT EXISTS warehouse_picklists (
    id INT AUTO_INCREMENT PRIMARY KEY,
    approval_id INT NOT NULL,
    status ENUM('reserved','packed','dispatched','cancelled') NOT NULL DEFAULT 'reserved',
    reserved_by INT NOT NULL,
    packed_by INT NULL,
    packed_at TIMESTAMP NULL,
    active_slot TINYINT GENERATED ALWAYS AS (IF(status = 'cancelled', NULL, 1)) STORED,
    UNIQUE KEY uq_open_picklist (approval_id, active_slot),
    FOREIGN KEY (approval_id) REFERENCES approval_orders(id),
    FOREIGN KEY (reserved_by) REFERENCES users(id),
    FOREIGN KEY (packed_by) REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS warehouse_pick_lines (
    picklist_id INT NOT NULL,
    lot_id INT NOT NULL,
    units INT UNSIGNED NOT NULL,
    PRIMARY KEY (picklist_id, lot_id),
    KEY ix_pick_lot (lot_id, picklist_id),
    FOREIGN KEY (picklist_id) REFERENCES warehouse_picklists(id),
    FOREIGN KEY (lot_id) REFERENCES warehouse_lots(id)
);
