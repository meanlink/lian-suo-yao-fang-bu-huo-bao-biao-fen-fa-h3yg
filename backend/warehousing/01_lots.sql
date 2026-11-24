CREATE TABLE IF NOT EXISTS warehouse_lots (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sku VARCHAR(40) NOT NULL,
    lot_code VARCHAR(50) NOT NULL,
    supplier_ref VARCHAR(80) NOT NULL,
    received_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_on DATE NOT NULL,
    temperature_band ENUM('ambient','chilled') NOT NULL,
    initial_units INT UNSIGNED NOT NULL,
    on_hand INT UNSIGNED NOT NULL,
    reserved INT UNSIGNED NOT NULL DEFAULT 0,
    state ENUM('available','recalled') NOT NULL DEFAULT 'available',
    registered_by INT NOT NULL,
    UNIQUE KEY uq_lot_sku_code (sku, lot_code),
    KEY ix_lot_selection (sku, state, expires_on, id),
    CONSTRAINT ck_lot_reservation CHECK (reserved <= on_hand),
    FOREIGN KEY (registered_by) REFERENCES users(id)
);
