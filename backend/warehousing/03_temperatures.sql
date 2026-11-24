CREATE TABLE IF NOT EXISTS warehouse_temperature_checks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    picklist_id INT NOT NULL,
    instrument_ref VARCHAR(60) NOT NULL,
    observed_c DECIMAL(5,2) NOT NULL,
    passed BOOLEAN NOT NULL,
    measured_by INT NOT NULL,
    measured_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY ix_pick_measurement (picklist_id, id),
    FOREIGN KEY (picklist_id) REFERENCES warehouse_picklists(id),
    FOREIGN KEY (measured_by) REFERENCES users(id)
);
