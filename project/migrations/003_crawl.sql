create table if not exists sources (
  id integer primary key autoincrement,
  keyword text not null,
  enabled integer default 1,
  interval_minutes integer default 60,
  last_run datetime,
  created_at datetime default current_timestamp
);

create table if not exists crawl_records (
  id integer primary key autoincrement,
  keyword text,
  title text,
  summary text,
  cover text,
  url text,
  source text,
  created_at datetime default current_timestamp
);

