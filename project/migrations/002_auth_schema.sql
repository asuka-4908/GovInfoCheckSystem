create table if not exists roles (
  id integer primary key autoincrement,
  name text unique not null,
  description text
);

drop table if exists users;

create table users (
  id integer primary key autoincrement,
  username text unique not null,
  password_hash text not null,
  role_id integer not null,
  created_at datetime default current_timestamp,
  foreign key (role_id) references roles(id)
);

create table if not exists settings (
  key text primary key,
  value text
);

insert into settings(key, value) values ('app_name', 'GovBiz Monitor AI')
  on conflict(key) do update set value=excluded.value;
insert into settings(key, value) values ('app_logo', '/static/images/logo.png')
  on conflict(key) do update set value=excluded.value;
