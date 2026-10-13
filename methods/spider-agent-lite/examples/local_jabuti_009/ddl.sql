--
-- PostgreSQL database dump
--

\restrict rLXKNXX6By4R2FhCTnyILdRLgB7r4kHHN8SSOF3VlZ2c0oL0hm4D520xHYZH5JV

-- Dumped from database version 14.20 (Ubuntu 14.20-0ubuntu0.22.04.1)
-- Dumped by pg_dump version 16.10

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: postgres
--

-- *not* creating schema, since initdb creates it


ALTER SCHEMA public OWNER TO postgres;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: catmat; Type: TABLE; Schema: public; Owner: datalake_user
--

CREATE TABLE public.catmat (
    catmat_id integer NOT NULL,
    codigo_catmat text,
    descricao_catmat text
);


ALTER TABLE public.catmat OWNER TO datalake_user;

--
-- Name: catmat_catmat_id_seq; Type: SEQUENCE; Schema: public; Owner: datalake_user
--

CREATE SEQUENCE public.catmat_catmat_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.catmat_catmat_id_seq OWNER TO datalake_user;

--
-- Name: catmat_catmat_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: datalake_user
--

ALTER SEQUENCE public.catmat_catmat_id_seq OWNED BY public.catmat.catmat_id;


--
-- Name: endereco; Type: TABLE; Schema: public; Owner: datalake_user
--

CREATE TABLE public.endereco (
    endereco_id integer NOT NULL,
    cep text,
    logradouro text,
    numero_do_logradouro text,
    bairro text,
    latitude numeric(20,4),
    longitude numeric(20,4),
    municipio_id integer,
    complemento text
);


ALTER TABLE public.endereco OWNER TO datalake_user;

--
-- Name: endereco_endereco_id_seq; Type: SEQUENCE; Schema: public; Owner: datalake_user
--

CREATE SEQUENCE public.endereco_endereco_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.endereco_endereco_id_seq OWNER TO datalake_user;

--
-- Name: endereco_endereco_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: datalake_user
--

ALTER SEQUENCE public.endereco_endereco_id_seq OWNED BY public.endereco.endereco_id;


--
-- Name: fabricante; Type: TABLE; Schema: public; Owner: datalake_user
--

CREATE TABLE public.fabricante (
    fabricante_id integer NOT NULL,
    cnpj_fabricante text,
    nome_fabricante text
);


ALTER TABLE public.fabricante OWNER TO datalake_user;

--
-- Name: fabricante_fabricante_id_seq; Type: SEQUENCE; Schema: public; Owner: datalake_user
--

CREATE SEQUENCE public.fabricante_fabricante_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.fabricante_fabricante_id_seq OWNER TO datalake_user;

--
-- Name: fabricante_fabricante_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: datalake_user
--

ALTER SEQUENCE public.fabricante_fabricante_id_seq OWNED BY public.fabricante.fabricante_id;


--
-- Name: fornecedor; Type: TABLE; Schema: public; Owner: datalake_user
--

CREATE TABLE public.fornecedor (
    fornecedor_id integer NOT NULL,
    cnpj_fornecedor text,
    nome_fornecedor text
);


ALTER TABLE public.fornecedor OWNER TO datalake_user;

--
-- Name: fornecedor_fornecedor_id_seq; Type: SEQUENCE; Schema: public; Owner: datalake_user
--

CREATE SEQUENCE public.fornecedor_fornecedor_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.fornecedor_fornecedor_id_seq OWNER TO datalake_user;

--
-- Name: fornecedor_fornecedor_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: datalake_user
--

ALTER SEQUENCE public.fornecedor_fornecedor_id_seq OWNED BY public.fornecedor.fornecedor_id;


--
-- Name: instituicao; Type: TABLE; Schema: public; Owner: datalake_user
--

CREATE TABLE public.instituicao (
    codigo_cnes text,
    codigo_unidade text,
    cnpj_instituicao text,
    nome_instituicao text,
    razao_social text,
    tipo_de_gestao text,
    codigo_tipo_unidade text,
    codigo_da_natureza_juridica text,
    codigo_natureza_organizacao text,
    descricao_natureza_organizacao text,
    codigo_nivel_hierarquia text,
    descricao_nivel_hierarquia text,
    codigo_esfera_administrativa text,
    descricao_esfera_administrativa text,
    codigo_atividade text,
    codigo_turno_atendimento text,
    descricao_turno_atendimento text,
    motivo_da_desabilitacao text,
    telefone text,
    email text,
    tem_centro_cirurgico text,
    tem_centro_obstetrico text,
    tem_centro_neonatal text,
    atendimento_hospitalar text,
    tem_servico_apoio text,
    atendimento_ambulatorial text,
    atendimento_sus text,
    origem_registro text,
    mantenedora_id integer,
    endereco_id integer,
    instituicao_id integer NOT NULL,
    descricao_tipo_unidade text,
    descricao_da_natureza_juridica text
);


ALTER TABLE public.instituicao OWNER TO datalake_user;

--
-- Name: instituicao_estoca_produto; Type: TABLE; Schema: public; Owner: datalake_user
--

CREATE TABLE public.instituicao_estoca_produto (
    instituicao_estoca_produto_id integer NOT NULL,
    data_de_posicao_no_estoque date,
    quantidade_do_item_em_estoque numeric(20,4),
    numero_do_lote text,
    data_de_validade timestamp with time zone,
    tipo_do_produto text,
    sigla_do_programa_de_saude text,
    descricao_do_programa_de_saude text,
    sigla_do_sistema_de_origem text,
    instituicao_id integer,
    produto_id integer
);


ALTER TABLE public.instituicao_estoca_produto OWNER TO datalake_user;

--
-- Name: instituicao_estoca_produto_instituicao_estoca_produto_id_seq; Type: SEQUENCE; Schema: public; Owner: datalake_user
--

CREATE SEQUENCE public.instituicao_estoca_produto_instituicao_estoca_produto_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.instituicao_estoca_produto_instituicao_estoca_produto_id_seq OWNER TO datalake_user;

--
-- Name: instituicao_estoca_produto_instituicao_estoca_produto_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: datalake_user
--

ALTER SEQUENCE public.instituicao_estoca_produto_instituicao_estoca_produto_id_seq OWNED BY public.instituicao_estoca_produto.instituicao_estoca_produto_id;


--
-- Name: instituicao_instituicao_id_seq; Type: SEQUENCE; Schema: public; Owner: datalake_user
--

CREATE SEQUENCE public.instituicao_instituicao_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.instituicao_instituicao_id_seq OWNER TO datalake_user;

--
-- Name: instituicao_instituicao_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: datalake_user
--

ALTER SEQUENCE public.instituicao_instituicao_id_seq OWNED BY public.instituicao.instituicao_id;


--
-- Name: leitos; Type: TABLE; Schema: public; Owner: datalake_user
--

CREATE TABLE public.leitos (
    leitos_id integer NOT NULL,
    data_de_competencia date,
    quantidade_leitos_gerais integer,
    quantidade_leitos_sus integer,
    quantidade_leitos_uti integer,
    quantidade_leitos_uti_sus integer,
    quantidade_leitos_uti_adulto integer,
    quantidade_leitos_uti_sus_adulto integer,
    quantidade_leitos_uti_pediatrico integer,
    quantidade_leitos_uti_sus_pediatrico integer,
    quantidade_leitos_uti_neonatal integer,
    quantidade_leitos_uti_sus_neonatal integer,
    quantidade_leitos_uti_queimado integer,
    quantidade_leitos_uti_sus_queimado integer,
    quantidade_leitos_uti_coronariana integer,
    quantidade_leitos_uti_sus_coronariana integer,
    instituicao_id integer
);


ALTER TABLE public.leitos OWNER TO datalake_user;

--
-- Name: leitos_leitos_id_seq; Type: SEQUENCE; Schema: public; Owner: datalake_user
--

CREATE SEQUENCE public.leitos_leitos_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.leitos_leitos_id_seq OWNER TO datalake_user;

--
-- Name: leitos_leitos_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: datalake_user
--

ALTER SEQUENCE public.leitos_leitos_id_seq OWNED BY public.leitos.leitos_id;


--
-- Name: macrorregiao_de_saude; Type: TABLE; Schema: public; Owner: datalake_user
--

CREATE TABLE public.macrorregiao_de_saude (
    codigo_macrorregiao_de_saude integer NOT NULL,
    macrorregiao_de_saude text,
    unidade_federativa_id text
);


ALTER TABLE public.macrorregiao_de_saude OWNER TO datalake_user;

--
-- Name: macrorregiao_de_saude_codigo_macrorregiao_de_saude_seq; Type: SEQUENCE; Schema: public; Owner: datalake_user
--

CREATE SEQUENCE public.macrorregiao_de_saude_codigo_macrorregiao_de_saude_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.macrorregiao_de_saude_codigo_macrorregiao_de_saude_seq OWNER TO datalake_user;

--
-- Name: macrorregiao_de_saude_codigo_macrorregiao_de_saude_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: datalake_user
--

ALTER SEQUENCE public.macrorregiao_de_saude_codigo_macrorregiao_de_saude_seq OWNED BY public.macrorregiao_de_saude.codigo_macrorregiao_de_saude;


--
-- Name: mantenedora; Type: TABLE; Schema: public; Owner: datalake_user
--

CREATE TABLE public.mantenedora (
    mantenedora_id integer NOT NULL,
    cnpj_mantenedora text,
    nome_mantenedora text,
    municipio_id integer
);


ALTER TABLE public.mantenedora OWNER TO datalake_user;

--
-- Name: mantenedora_compra_produto; Type: TABLE; Schema: public; Owner: datalake_user
--

CREATE TABLE public.mantenedora_compra_produto (
    mantenedora_compra_produto_id integer NOT NULL,
    data_de_compra date,
    data_de_insercao date,
    modalidade_de_compra text,
    capacidade numeric(20,4),
    unidade_de_medida text,
    tipo_da_compra text,
    quantidade_de_itens numeric(20,4),
    preco_unitario numeric(20,4),
    preco_total numeric(20,4),
    fornecedor_id integer,
    fabricante_id integer,
    produto_id integer,
    mantenedora_id integer
);


ALTER TABLE public.mantenedora_compra_produto OWNER TO datalake_user;

--
-- Name: mantenedora_compra_produto_mantenedora_compra_produto_id_seq; Type: SEQUENCE; Schema: public; Owner: datalake_user
--

CREATE SEQUENCE public.mantenedora_compra_produto_mantenedora_compra_produto_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.mantenedora_compra_produto_mantenedora_compra_produto_id_seq OWNER TO datalake_user;

--
-- Name: mantenedora_compra_produto_mantenedora_compra_produto_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: datalake_user
--

ALTER SEQUENCE public.mantenedora_compra_produto_mantenedora_compra_produto_id_seq OWNED BY public.mantenedora_compra_produto.mantenedora_compra_produto_id;


--
-- Name: mantenedora_mantenedora_id_seq; Type: SEQUENCE; Schema: public; Owner: datalake_user
--

CREATE SEQUENCE public.mantenedora_mantenedora_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.mantenedora_mantenedora_id_seq OWNER TO datalake_user;

--
-- Name: mantenedora_mantenedora_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: datalake_user
--

ALTER SEQUENCE public.mantenedora_mantenedora_id_seq OWNED BY public.mantenedora.mantenedora_id;


--
-- Name: municipio; Type: TABLE; Schema: public; Owner: datalake_user
--

CREATE TABLE public.municipio (
    codigo_do_municipio integer NOT NULL,
    municipio text,
    sigla_uf text,
    populacao integer,
    regiao_de_saude_id text
);


ALTER TABLE public.municipio OWNER TO datalake_user;

--
-- Name: municipio_codigo_do_municipio_seq; Type: SEQUENCE; Schema: public; Owner: datalake_user
--

CREATE SEQUENCE public.municipio_codigo_do_municipio_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.municipio_codigo_do_municipio_seq OWNER TO datalake_user;

--
-- Name: municipio_codigo_do_municipio_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: datalake_user
--

ALTER SEQUENCE public.municipio_codigo_do_municipio_seq OWNED BY public.municipio.codigo_do_municipio;


--
-- Name: mv_estoque_mais_recente; Type: MATERIALIZED VIEW; Schema: public; Owner: datalake_user
--

CREATE MATERIALIZED VIEW public.mv_estoque_mais_recente AS
 SELECT DISTINCT ON (instituicao_estoca_produto.instituicao_id, instituicao_estoca_produto.produto_id) instituicao_estoca_produto.instituicao_id,
    instituicao_estoca_produto.produto_id,
    instituicao_estoca_produto.data_de_posicao_no_estoque,
    instituicao_estoca_produto.quantidade_do_item_em_estoque,
    instituicao_estoca_produto.data_de_validade,
    instituicao_estoca_produto.numero_do_lote,
    instituicao_estoca_produto.tipo_do_produto,
    instituicao_estoca_produto.sigla_do_programa_de_saude,
    instituicao_estoca_produto.descricao_do_programa_de_saude,
    instituicao_estoca_produto.sigla_do_sistema_de_origem
   FROM public.instituicao_estoca_produto
  ORDER BY instituicao_estoca_produto.instituicao_id, instituicao_estoca_produto.produto_id, instituicao_estoca_produto.data_de_posicao_no_estoque DESC
  WITH NO DATA;


ALTER MATERIALIZED VIEW public.mv_estoque_mais_recente OWNER TO datalake_user;

--
-- Name: mv_leitos_mais_recente; Type: MATERIALIZED VIEW; Schema: public; Owner: datalake_user
--

CREATE MATERIALIZED VIEW public.mv_leitos_mais_recente AS
 SELECT DISTINCT ON (leitos.instituicao_id) leitos.instituicao_id,
    leitos.data_de_competencia,
    leitos.quantidade_leitos_gerais,
    leitos.quantidade_leitos_sus,
    leitos.quantidade_leitos_uti,
    leitos.quantidade_leitos_uti_sus,
    leitos.quantidade_leitos_uti_adulto,
    leitos.quantidade_leitos_uti_sus_adulto,
    leitos.quantidade_leitos_uti_pediatrico,
    leitos.quantidade_leitos_uti_sus_pediatrico,
    leitos.quantidade_leitos_uti_neonatal,
    leitos.quantidade_leitos_uti_sus_neonatal,
    leitos.quantidade_leitos_uti_queimado,
    leitos.quantidade_leitos_uti_sus_queimado,
    leitos.quantidade_leitos_uti_coronariana,
    leitos.quantidade_leitos_uti_sus_coronariana
   FROM public.leitos
  ORDER BY leitos.instituicao_id, leitos.data_de_competencia DESC
  WITH NO DATA;


ALTER MATERIALIZED VIEW public.mv_leitos_mais_recente OWNER TO datalake_user;

--
-- Name: produto; Type: TABLE; Schema: public; Owner: datalake_user
--

CREATE TABLE public.produto (
    produto_id integer NOT NULL,
    anvisa text,
    generico text,
    codigo_catmat text,
    catmat_id integer
);


ALTER TABLE public.produto OWNER TO datalake_user;

--
-- Name: produto_produto_id_seq; Type: SEQUENCE; Schema: public; Owner: datalake_user
--

CREATE SEQUENCE public.produto_produto_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.produto_produto_id_seq OWNER TO datalake_user;

--
-- Name: produto_produto_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: datalake_user
--

ALTER SEQUENCE public.produto_produto_id_seq OWNED BY public.produto.produto_id;


--
-- Name: regiao_de_saude; Type: TABLE; Schema: public; Owner: datalake_user
--

CREATE TABLE public.regiao_de_saude (
    codigo_da_regiao_de_saude integer NOT NULL,
    regiao_de_saude text,
    macrorregiao_de_saude_id text
);


ALTER TABLE public.regiao_de_saude OWNER TO datalake_user;

--
-- Name: regiao_de_saude_codigo_da_regiao_de_saude_seq; Type: SEQUENCE; Schema: public; Owner: datalake_user
--

CREATE SEQUENCE public.regiao_de_saude_codigo_da_regiao_de_saude_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.regiao_de_saude_codigo_da_regiao_de_saude_seq OWNER TO datalake_user;

--
-- Name: regiao_de_saude_codigo_da_regiao_de_saude_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: datalake_user
--

ALTER SEQUENCE public.regiao_de_saude_codigo_da_regiao_de_saude_seq OWNED BY public.regiao_de_saude.codigo_da_regiao_de_saude;


--
-- Name: regiao_do_brasil; Type: TABLE; Schema: public; Owner: datalake_user
--

CREATE TABLE public.regiao_do_brasil (
    codigo_da_regiao_do_brasil integer NOT NULL,
    regiao_do_brasil text
);


ALTER TABLE public.regiao_do_brasil OWNER TO datalake_user;

--
-- Name: regiao_do_brasil_codigo_da_regiao_do_brasil_seq; Type: SEQUENCE; Schema: public; Owner: datalake_user
--

CREATE SEQUENCE public.regiao_do_brasil_codigo_da_regiao_do_brasil_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.regiao_do_brasil_codigo_da_regiao_do_brasil_seq OWNER TO datalake_user;

--
-- Name: regiao_do_brasil_codigo_da_regiao_do_brasil_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: datalake_user
--

ALTER SEQUENCE public.regiao_do_brasil_codigo_da_regiao_do_brasil_seq OWNED BY public.regiao_do_brasil.codigo_da_regiao_do_brasil;


--
-- Name: unidade_federativa; Type: TABLE; Schema: public; Owner: datalake_user
--

CREATE TABLE public.unidade_federativa (
    codigo_da_unidade_federativa integer NOT NULL,
    unidade_federativa text,
    sigla_unidade_federativa text,
    regiao_do_brasil_id text
);


ALTER TABLE public.unidade_federativa OWNER TO datalake_user;

--
-- Name: unidade_federativa_codigo_da_unidade_federativa_seq; Type: SEQUENCE; Schema: public; Owner: datalake_user
--

CREATE SEQUENCE public.unidade_federativa_codigo_da_unidade_federativa_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.unidade_federativa_codigo_da_unidade_federativa_seq OWNER TO datalake_user;

--
-- Name: unidade_federativa_codigo_da_unidade_federativa_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: datalake_user
--

ALTER SEQUENCE public.unidade_federativa_codigo_da_unidade_federativa_seq OWNED BY public.unidade_federativa.codigo_da_unidade_federativa;


--
-- Name: v_endereco_completo; Type: VIEW; Schema: public; Owner: datalake_user
--

CREATE VIEW public.v_endereco_completo AS
 SELECT e.endereco_id,
    e.cep,
    e.logradouro,
    e.numero_do_logradouro,
    e.bairro,
    e.complemento,
    e.latitude,
    e.longitude,
    e.municipio_id,
    m.codigo_do_municipio,
    m.municipio,
    m.sigla_uf,
    m.populacao,
    uf.codigo_da_unidade_federativa,
    uf.unidade_federativa,
    uf.sigla_unidade_federativa,
    rb.codigo_da_regiao_do_brasil,
    rb.regiao_do_brasil,
    rs.codigo_da_regiao_de_saude,
    rs.regiao_de_saude,
    macro.codigo_macrorregiao_de_saude,
    macro.macrorregiao_de_saude
   FROM (((((public.endereco e
     JOIN public.municipio m ON ((m.codigo_do_municipio = e.municipio_id)))
     JOIN public.regiao_de_saude rs ON ((rs.codigo_da_regiao_de_saude = (m.regiao_de_saude_id)::integer)))
     JOIN public.macrorregiao_de_saude macro ON ((macro.codigo_macrorregiao_de_saude = (rs.macrorregiao_de_saude_id)::integer)))
     JOIN public.unidade_federativa uf ON ((uf.codigo_da_unidade_federativa = (macro.unidade_federativa_id)::integer)))
     JOIN public.regiao_do_brasil rb ON ((rb.codigo_da_regiao_do_brasil = (uf.regiao_do_brasil_id)::integer)));


ALTER VIEW public.v_endereco_completo OWNER TO datalake_user;

--
-- Name: v_produto_completo; Type: VIEW; Schema: public; Owner: datalake_user
--

CREATE VIEW public.v_produto_completo AS
 SELECT p.produto_id,
    p.catmat_id,
    p.anvisa,
    p.generico,
    p.codigo_catmat,
    c.descricao_catmat
   FROM (public.produto p
     JOIN public.catmat c ON ((c.catmat_id = p.catmat_id)));


ALTER VIEW public.v_produto_completo OWNER TO datalake_user;

--
-- Name: catmat catmat_id; Type: DEFAULT; Schema: public; Owner: datalake_user
--

ALTER TABLE ONLY public.catmat ALTER COLUMN catmat_id SET DEFAULT nextval('public.catmat_catmat_id_seq'::regclass);


--
-- Name: endereco endereco_id; Type: DEFAULT; Schema: public; Owner: datalake_user
--

ALTER TABLE ONLY public.endereco ALTER COLUMN endereco_id SET DEFAULT nextval('public.endereco_endereco_id_seq'::regclass);


--
-- Name: fabricante fabricante_id; Type: DEFAULT; Schema: public; Owner: datalake_user
--

ALTER TABLE ONLY public.fabricante ALTER COLUMN fabricante_id SET DEFAULT nextval('public.fabricante_fabricante_id_seq'::regclass);


--
-- Name: fornecedor fornecedor_id; Type: DEFAULT; Schema: public; Owner: datalake_user
--

ALTER TABLE ONLY public.fornecedor ALTER COLUMN fornecedor_id SET DEFAULT nextval('public.fornecedor_fornecedor_id_seq'::regclass);


--
-- Name: instituicao instituicao_id; Type: DEFAULT; Schema: public; Owner: datalake_user
--

ALTER TABLE ONLY public.instituicao ALTER COLUMN instituicao_id SET DEFAULT nextval('public.instituicao_instituicao_id_seq'::regclass);


--
-- Name: instituicao_estoca_produto instituicao_estoca_produto_id; Type: DEFAULT; Schema: public; Owner: datalake_user
--

ALTER TABLE ONLY public.instituicao_estoca_produto ALTER COLUMN instituicao_estoca_produto_id SET DEFAULT nextval('public.instituicao_estoca_produto_instituicao_estoca_produto_id_seq'::regclass);


--
-- Name: leitos leitos_id; Type: DEFAULT; Schema: public; Owner: datalake_user
--

ALTER TABLE ONLY public.leitos ALTER COLUMN leitos_id SET DEFAULT nextval('public.leitos_leitos_id_seq'::regclass);


--
-- Name: macrorregiao_de_saude codigo_macrorregiao_de_saude; Type: DEFAULT; Schema: public; Owner: datalake_user
--

ALTER TABLE ONLY public.macrorregiao_de_saude ALTER COLUMN codigo_macrorregiao_de_saude SET DEFAULT nextval('public.macrorregiao_de_saude_codigo_macrorregiao_de_saude_seq'::regclass);


--
-- Name: mantenedora mantenedora_id; Type: DEFAULT; Schema: public; Owner: datalake_user
--

ALTER TABLE ONLY public.mantenedora ALTER COLUMN mantenedora_id SET DEFAULT nextval('public.mantenedora_mantenedora_id_seq'::regclass);


--
-- Name: mantenedora_compra_produto mantenedora_compra_produto_id; Type: DEFAULT; Schema: public; Owner: datalake_user
--

ALTER TABLE ONLY public.mantenedora_compra_produto ALTER COLUMN mantenedora_compra_produto_id SET DEFAULT nextval('public.mantenedora_compra_produto_mantenedora_compra_produto_id_seq'::regclass);


--
-- Name: municipio codigo_do_municipio; Type: DEFAULT; Schema: public; Owner: datalake_user
--

ALTER TABLE ONLY public.municipio ALTER COLUMN codigo_do_municipio SET DEFAULT nextval('public.municipio_codigo_do_municipio_seq'::regclass);


--
-- Name: produto produto_id; Type: DEFAULT; Schema: public; Owner: datalake_user
--

ALTER TABLE ONLY public.produto ALTER COLUMN produto_id SET DEFAULT nextval('public.produto_produto_id_seq'::regclass);


--
-- Name: regiao_de_saude codigo_da_regiao_de_saude; Type: DEFAULT; Schema: public; Owner: datalake_user
--

ALTER TABLE ONLY public.regiao_de_saude ALTER COLUMN codigo_da_regiao_de_saude SET DEFAULT nextval('public.regiao_de_saude_codigo_da_regiao_de_saude_seq'::regclass);


--
-- Name: regiao_do_brasil codigo_da_regiao_do_brasil; Type: DEFAULT; Schema: public; Owner: datalake_user
--

ALTER TABLE ONLY public.regiao_do_brasil ALTER COLUMN codigo_da_regiao_do_brasil SET DEFAULT nextval('public.regiao_do_brasil_codigo_da_regiao_do_brasil_seq'::regclass);


--
-- Name: unidade_federativa codigo_da_unidade_federativa; Type: DEFAULT; Schema: public; Owner: datalake_user
--

ALTER TABLE ONLY public.unidade_federativa ALTER COLUMN codigo_da_unidade_federativa SET DEFAULT nextval('public.unidade_federativa_codigo_da_unidade_federativa_seq'::regclass);


--
-- Name: catmat catmat_pkey; Type: CONSTRAINT; Schema: public; Owner: datalake_user
--

ALTER TABLE ONLY public.catmat
    ADD CONSTRAINT catmat_pkey PRIMARY KEY (catmat_id);


--
-- Name: endereco endereco_pkey; Type: CONSTRAINT; Schema: public; Owner: datalake_user
--

ALTER TABLE ONLY public.endereco
    ADD CONSTRAINT endereco_pkey PRIMARY KEY (endereco_id);


--
-- Name: fabricante fabricante_pkey; Type: CONSTRAINT; Schema: public; Owner: datalake_user
--

ALTER TABLE ONLY public.fabricante
    ADD CONSTRAINT fabricante_pkey PRIMARY KEY (fabricante_id);


--
-- Name: fornecedor fornecedor_pkey; Type: CONSTRAINT; Schema: public; Owner: datalake_user
--

ALTER TABLE ONLY public.fornecedor
    ADD CONSTRAINT fornecedor_pkey PRIMARY KEY (fornecedor_id);


--
-- Name: instituicao_estoca_produto instituicao_estoca_produto_pkey; Type: CONSTRAINT; Schema: public; Owner: datalake_user
--

ALTER TABLE ONLY public.instituicao_estoca_produto
    ADD CONSTRAINT instituicao_estoca_produto_pkey PRIMARY KEY (instituicao_estoca_produto_id);


--
-- Name: instituicao instituicao_pkey; Type: CONSTRAINT; Schema: public; Owner: datalake_user
--

ALTER TABLE ONLY public.instituicao
    ADD CONSTRAINT instituicao_pkey PRIMARY KEY (instituicao_id);


--
-- Name: leitos leitos_pkey; Type: CONSTRAINT; Schema: public; Owner: datalake_user
--

ALTER TABLE ONLY public.leitos
    ADD CONSTRAINT leitos_pkey PRIMARY KEY (leitos_id);


--
-- Name: macrorregiao_de_saude macrorregiao_de_saude_pkey; Type: CONSTRAINT; Schema: public; Owner: datalake_user
--

ALTER TABLE ONLY public.macrorregiao_de_saude
    ADD CONSTRAINT macrorregiao_de_saude_pkey PRIMARY KEY (codigo_macrorregiao_de_saude);


--
-- Name: mantenedora_compra_produto mantenedora_compra_produto_pkey; Type: CONSTRAINT; Schema: public; Owner: datalake_user
--

ALTER TABLE ONLY public.mantenedora_compra_produto
    ADD CONSTRAINT mantenedora_compra_produto_pkey PRIMARY KEY (mantenedora_compra_produto_id);


--
-- Name: mantenedora mantenedora_pkey; Type: CONSTRAINT; Schema: public; Owner: datalake_user
--

ALTER TABLE ONLY public.mantenedora
    ADD CONSTRAINT mantenedora_pkey PRIMARY KEY (mantenedora_id);


--
-- Name: municipio municipio_pkey; Type: CONSTRAINT; Schema: public; Owner: datalake_user
--

ALTER TABLE ONLY public.municipio
    ADD CONSTRAINT municipio_pkey PRIMARY KEY (codigo_do_municipio);


--
-- Name: produto produto_pkey; Type: CONSTRAINT; Schema: public; Owner: datalake_user
--

ALTER TABLE ONLY public.produto
    ADD CONSTRAINT produto_pkey PRIMARY KEY (produto_id);


--
-- Name: regiao_de_saude regiao_de_saude_pkey; Type: CONSTRAINT; Schema: public; Owner: datalake_user
--

ALTER TABLE ONLY public.regiao_de_saude
    ADD CONSTRAINT regiao_de_saude_pkey PRIMARY KEY (codigo_da_regiao_de_saude);


--
-- Name: regiao_do_brasil regiao_do_brasil_pkey; Type: CONSTRAINT; Schema: public; Owner: datalake_user
--

ALTER TABLE ONLY public.regiao_do_brasil
    ADD CONSTRAINT regiao_do_brasil_pkey PRIMARY KEY (codigo_da_regiao_do_brasil);


--
-- Name: unidade_federativa unidade_federativa_pkey; Type: CONSTRAINT; Schema: public; Owner: datalake_user
--

ALTER TABLE ONLY public.unidade_federativa
    ADD CONSTRAINT unidade_federativa_pkey PRIMARY KEY (codigo_da_unidade_federativa);


--
-- Name: idx_catmat_codigo; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE UNIQUE INDEX idx_catmat_codigo ON public.catmat USING btree (codigo_catmat);


--
-- Name: idx_endereco_chave_negocio; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE UNIQUE INDEX idx_endereco_chave_negocio ON public.endereco USING btree (cep, logradouro, numero_do_logradouro);


--
-- Name: idx_endereco_coords_nulos; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE INDEX idx_endereco_coords_nulos ON public.endereco USING btree (endereco_id) WHERE ((latitude IS NULL) OR (longitude IS NULL));


--
-- Name: idx_endereco_municipio_fk; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE INDEX idx_endereco_municipio_fk ON public.endereco USING btree (municipio_id);


--
-- Name: idx_fabricante_cnpj; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE UNIQUE INDEX idx_fabricante_cnpj ON public.fabricante USING btree (cnpj_fabricante);


--
-- Name: idx_fornecedor_cnpj; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE UNIQUE INDEX idx_fornecedor_cnpj ON public.fornecedor USING btree (cnpj_fornecedor);


--
-- Name: idx_iep_inst_data_positivo; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE INDEX idx_iep_inst_data_positivo ON public.instituicao_estoca_produto USING btree (instituicao_id, data_de_posicao_no_estoque DESC) WHERE (quantidade_do_item_em_estoque > (0)::numeric);


--
-- Name: idx_iep_inst_prod_data; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE INDEX idx_iep_inst_prod_data ON public.instituicao_estoca_produto USING btree (instituicao_id, produto_id, data_de_posicao_no_estoque DESC);


--
-- Name: idx_iep_instituicao_produto; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE INDEX idx_iep_instituicao_produto ON public.instituicao_estoca_produto USING btree (instituicao_id, produto_id);


--
-- Name: idx_iep_produto_fk; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE INDEX idx_iep_produto_fk ON public.instituicao_estoca_produto USING btree (produto_id);


--
-- Name: idx_iep_validade_positivo; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE INDEX idx_iep_validade_positivo ON public.instituicao_estoca_produto USING btree (data_de_validade) WHERE ((data_de_validade IS NOT NULL) AND (quantidade_do_item_em_estoque > (0)::numeric));


--
-- Name: idx_instituicao_cnpj; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE INDEX idx_instituicao_cnpj ON public.instituicao USING btree (cnpj_instituicao);


--
-- Name: idx_instituicao_codigo_cnes; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE UNIQUE INDEX idx_instituicao_codigo_cnes ON public.instituicao USING btree (codigo_cnes);


--
-- Name: idx_instituicao_endereco_fk; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE INDEX idx_instituicao_endereco_fk ON public.instituicao USING btree (endereco_id);


--
-- Name: idx_instituicao_gestao_natureza_ativo; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE INDEX idx_instituicao_gestao_natureza_ativo ON public.instituicao USING btree (tipo_de_gestao, codigo_da_natureza_juridica) WHERE (motivo_da_desabilitacao IS NULL);


--
-- Name: idx_instituicao_mantenedora_fk; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE INDEX idx_instituicao_mantenedora_fk ON public.instituicao USING btree (mantenedora_id);


--
-- Name: idx_instituicao_nome_lower; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE INDEX idx_instituicao_nome_lower ON public.instituicao USING btree (lower(nome_instituicao));


--
-- Name: idx_instituicao_tipo_unidade_ativo; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE INDEX idx_instituicao_tipo_unidade_ativo ON public.instituicao USING btree (codigo_tipo_unidade) WHERE (motivo_da_desabilitacao IS NULL);


--
-- Name: idx_leitos_data_competencia; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE INDEX idx_leitos_data_competencia ON public.leitos USING btree (data_de_competencia DESC);


--
-- Name: idx_leitos_gerais_not_null; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE INDEX idx_leitos_gerais_not_null ON public.leitos USING btree (quantidade_leitos_gerais DESC, instituicao_id) WHERE (quantidade_leitos_gerais IS NOT NULL);


--
-- Name: idx_leitos_inst_data_covering; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE INDEX idx_leitos_inst_data_covering ON public.leitos USING btree (instituicao_id, data_de_competencia DESC) INCLUDE (quantidade_leitos_gerais, quantidade_leitos_sus, quantidade_leitos_uti, quantidade_leitos_uti_sus, quantidade_leitos_uti_adulto, quantidade_leitos_uti_sus_adulto, quantidade_leitos_uti_pediatrico, quantidade_leitos_uti_sus_pediatrico, quantidade_leitos_uti_neonatal, quantidade_leitos_uti_sus_neonatal, quantidade_leitos_uti_queimado, quantidade_leitos_uti_sus_queimado, quantidade_leitos_uti_coronariana, quantidade_leitos_uti_sus_coronariana);


--
-- Name: idx_macrorregiao_codigo; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE UNIQUE INDEX idx_macrorregiao_codigo ON public.macrorregiao_de_saude USING btree (codigo_macrorregiao_de_saude);


--
-- Name: idx_macrorregiao_uf_fk; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE INDEX idx_macrorregiao_uf_fk ON public.macrorregiao_de_saude USING btree (unidade_federativa_id);


--
-- Name: idx_mantenedora_cnpj; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE UNIQUE INDEX idx_mantenedora_cnpj ON public.mantenedora USING btree (cnpj_mantenedora);


--
-- Name: idx_mantenedora_municipio_fk; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE INDEX idx_mantenedora_municipio_fk ON public.mantenedora USING btree (municipio_id);


--
-- Name: idx_mcp_data_compra; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE INDEX idx_mcp_data_compra ON public.mantenedora_compra_produto USING btree (data_de_compra DESC);


--
-- Name: idx_mcp_fabricante_fk; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE INDEX idx_mcp_fabricante_fk ON public.mantenedora_compra_produto USING btree (fabricante_id);


--
-- Name: idx_mcp_fornecedor_data_covering; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE INDEX idx_mcp_fornecedor_data_covering ON public.mantenedora_compra_produto USING btree (fornecedor_id, data_de_compra DESC) INCLUDE (preco_total, quantidade_de_itens);


--
-- Name: idx_mcp_mantenedora_fk; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE INDEX idx_mcp_mantenedora_fk ON public.mantenedora_compra_produto USING btree (mantenedora_id);


--
-- Name: idx_mcp_precos_completos; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE INDEX idx_mcp_precos_completos ON public.mantenedora_compra_produto USING btree (produto_id, data_de_compra) WHERE ((preco_total IS NOT NULL) AND (preco_unitario IS NOT NULL) AND (quantidade_de_itens IS NOT NULL));


--
-- Name: idx_mcp_produto_data_covering; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE INDEX idx_mcp_produto_data_covering ON public.mantenedora_compra_produto USING btree (produto_id, data_de_compra DESC) INCLUDE (quantidade_de_itens, preco_unitario, preco_total, fabricante_id);


--
-- Name: idx_municipio_codigo; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE UNIQUE INDEX idx_municipio_codigo ON public.municipio USING btree (codigo_do_municipio);


--
-- Name: idx_municipio_nome_uf; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE UNIQUE INDEX idx_municipio_nome_uf ON public.municipio USING btree (municipio, sigla_uf);


--
-- Name: idx_municipio_regiao_saude_fk; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE INDEX idx_municipio_regiao_saude_fk ON public.municipio USING btree (regiao_de_saude_id);


--
-- Name: idx_produto_catmat_fk; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE INDEX idx_produto_catmat_fk ON public.produto USING btree (catmat_id);


--
-- Name: idx_produto_chave_negocio; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE UNIQUE INDEX idx_produto_chave_negocio ON public.produto USING btree (catmat_id, anvisa, generico);


--
-- Name: idx_produto_generico_upper; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE INDEX idx_produto_generico_upper ON public.produto USING btree (upper(generico));


--
-- Name: idx_regiao_brasil_codigo; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE UNIQUE INDEX idx_regiao_brasil_codigo ON public.regiao_do_brasil USING btree (codigo_da_regiao_do_brasil);


--
-- Name: idx_regiao_saude_codigo; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE UNIQUE INDEX idx_regiao_saude_codigo ON public.regiao_de_saude USING btree (codigo_da_regiao_de_saude);


--
-- Name: idx_regiao_saude_macro_fk; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE INDEX idx_regiao_saude_macro_fk ON public.regiao_de_saude USING btree (macrorregiao_de_saude_id);


--
-- Name: idx_uf_codigo; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE UNIQUE INDEX idx_uf_codigo ON public.unidade_federativa USING btree (codigo_da_unidade_federativa);


--
-- Name: idx_uf_regiao_pais_fk; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE INDEX idx_uf_regiao_pais_fk ON public.unidade_federativa USING btree (regiao_do_brasil_id);


--
-- Name: idx_uf_sigla; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE INDEX idx_uf_sigla ON public.unidade_federativa USING btree (sigla_unidade_federativa);


--
-- Name: mv_estoque_mais_recente_data_de_validade_idx; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE INDEX mv_estoque_mais_recente_data_de_validade_idx ON public.mv_estoque_mais_recente USING btree (data_de_validade) WHERE ((data_de_validade IS NOT NULL) AND (quantidade_do_item_em_estoque > (0)::numeric));


--
-- Name: mv_estoque_mais_recente_instituicao_id_idx; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE INDEX mv_estoque_mais_recente_instituicao_id_idx ON public.mv_estoque_mais_recente USING btree (instituicao_id) WHERE (quantidade_do_item_em_estoque > (0)::numeric);


--
-- Name: mv_estoque_mais_recente_instituicao_id_produto_id_idx; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE UNIQUE INDEX mv_estoque_mais_recente_instituicao_id_produto_id_idx ON public.mv_estoque_mais_recente USING btree (instituicao_id, produto_id);


--
-- Name: mv_leitos_mais_recente_instituicao_id_idx; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE UNIQUE INDEX mv_leitos_mais_recente_instituicao_id_idx ON public.mv_leitos_mais_recente USING btree (instituicao_id);


--
-- Name: mv_leitos_mais_recente_quantidade_leitos_gerais_idx; Type: INDEX; Schema: public; Owner: datalake_user
--

CREATE INDEX mv_leitos_mais_recente_quantidade_leitos_gerais_idx ON public.mv_leitos_mais_recente USING btree (quantidade_leitos_gerais DESC) WHERE (quantidade_leitos_gerais IS NOT NULL);


--
-- Name: SCHEMA public; Type: ACL; Schema: -; Owner: postgres
--

REVOKE USAGE ON SCHEMA public FROM PUBLIC;
GRANT ALL ON SCHEMA public TO PUBLIC;


--
-- PostgreSQL database dump complete
--

\unrestrict rLXKNXX6By4R2FhCTnyILdRLgB7r4kHHN8SSOF3VlZ2c0oL0hm4D520xHYZH5JV

