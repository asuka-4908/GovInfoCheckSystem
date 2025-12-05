create table if not exists crawl_details (
  id integer primary key autoincrement,
  record_id integer not null,
  url text not null,
  content_text text,
  content_html text,
  created_at datetime default current_timestamp,
  foreign key (record_id) references crawl_records(id)
);
