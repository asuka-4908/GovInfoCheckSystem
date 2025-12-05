create table if not exists crawlers (
  id integer primary key autoincrement,
  name text unique not null,
  module text,
  callable text,
  config text,
  enabled integer default 1,
  created_at datetime default current_timestamp
);

-- optional linking from sources to a specific crawler
-- this may fail if the column already exists; ignore errors
alter table sources add column crawler_name text;
