CREATE TABLE IF NOT EXISTS expiry_actions (
  snapshot_id INT PRIMARY KEY REFERENCES inventory_snapshots(id),
  action ENUM('quarantined','returned') NOT NULL,
  note VARCHAR(255) NOT NULL,
  actor_id INT NOT NULL REFERENCES users(id),
  recorded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS shortage_cases (
  snapshot_id INT PRIMARY KEY REFERENCES inventory_snapshots(id),
  status ENUM('open','resolved') NOT NULL DEFAULT 'open',
  note VARCHAR(255) NOT NULL,
  opened_by INT NOT NULL REFERENCES users(id),
  opened_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  resolution VARCHAR(255) NULL,
  resolved_by INT NULL REFERENCES users(id),
  resolved_at TIMESTAMP NULL
);
CREATE TABLE IF NOT EXISTS report_subscriptions (
  id INT PRIMARY KEY AUTO_INCREMENT,
  store_code VARCHAR(40) NOT NULL,
  recipient_id INT NOT NULL REFERENCES users(id),
  delivery_hour INT NOT NULL CHECK(delivery_hour BETWEEN 0 AND 23),
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  created_on DATE NOT NULL,
  UNIQUE KEY store_recipient_hour (store_code,recipient_id,delivery_hour)
);
CREATE TABLE IF NOT EXISTS report_deliveries (
  id INT PRIMARY KEY AUTO_INCREMENT,
  subscription_id INT NOT NULL REFERENCES report_subscriptions(id),
  report_date DATE NOT NULL,
  payload JSON NOT NULL,
  delivered_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY daily_delivery (subscription_id,report_date)
);
CREATE TABLE IF NOT EXISTS receipt_exceptions (
  dispatch_id INT PRIMARY KEY REFERENCES dispatch_records(id),
  reason VARCHAR(255) NOT NULL,
  opened_by INT NOT NULL REFERENCES users(id),
  opened_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  closed_by INT NULL REFERENCES users(id),
  closed_at TIMESTAMP NULL
);
