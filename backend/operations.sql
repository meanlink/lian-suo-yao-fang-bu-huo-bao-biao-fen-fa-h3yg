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
CREATE TABLE IF NOT EXISTS sales_corrections (
  id INT PRIMARY KEY AUTO_INCREMENT,
  snapshot_id INT NOT NULL,
  revision INT NOT NULL,
  daily_sales JSON NOT NULL,
  old_recommended_qty INT NULL,
  new_recommended_qty INT NULL,
  replacement_approval_id INT NULL,
  note VARCHAR(255) NOT NULL DEFAULT '',
  actor_id INT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY snapshot_revision (snapshot_id,revision),
  FOREIGN KEY (snapshot_id) REFERENCES inventory_snapshots(id),
  FOREIGN KEY (actor_id) REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS sales_correction_orders (
  id INT PRIMARY KEY AUTO_INCREMENT,
  correction_id INT NOT NULL REFERENCES sales_corrections(id),
  approval_id INT NOT NULL REFERENCES approval_orders(id),
  previous_status VARCHAR(20) NOT NULL,
  outcome ENUM('voided','kept_dispatched') NOT NULL,
  UNIQUE KEY correction_approval (correction_id,approval_id)
);
CREATE TABLE IF NOT EXISTS receipt_exceptions (
  dispatch_id INT PRIMARY KEY REFERENCES dispatch_records(id),
  reason VARCHAR(255) NOT NULL,
  opened_by INT NOT NULL REFERENCES users(id),
  opened_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  closed_by INT NULL REFERENCES users(id),
  closed_at TIMESTAMP NULL
);
