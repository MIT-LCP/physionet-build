- [1. Setting up your system for the first time](#1-setting-up-your-system-for-the-first-time)
  - [1.1 MacOS](#11-macos)
    - [1.1.1 Install HomeBrew](#111-install-homebrew)
    - [1.1.2 Install Python](#112-install-python)
    - [1.1.3 Install git](#113-install-git)
    - [1.1.4 Install sqlite3](#114-install-sqlite3)
    - [1.1.5 Install VSCode](#115-install-vscode)
    - [1.1.6 Clone the Project Locally](#116-clone-the-project-locally)
    - [1.1.7 Install and Create Virtual Environment](#117-install-and-create-virtual-environment)
    - [1.1.8 Install requirements](#118-install-requirements)
    - [1.1.9 Run the project](#119-run-the-project)
    - [1.1.9.1 Open terminal and navigate inside the project directory](#1191-open-terminal-and-navigate-inside-the-project-directory)
    - [1.1.9.2  Activate virtual python environment.](#1192--activate-virtual-python-environment)
    - [1.1.9.3 Copy .env.example file to .env](#1193-copy-envexample-file-to-env)
    - [1.1.9.4 Run the following commands to setup the database](#1194-run-the-following-commands-to-setup-the-database)
    - [1.1.10 Start the server(Finally)](#1110-start-the-serverfinally)
  - [1.2 Windows](#12-windows)
    - [1.2.1 Install Python3](#121-install-python3)
    - [1.2.2 Install git Bash](#122-install-git-bash)
    - [1.2.3 Install VSCode](#123-install-vscode)
    - [1.2.4 Clone the Project Locally](#124-clone-the-project-locally)
    - [1.2.5 Install and Create Virtual Environment](#125-install-and-create-virtual-environment)
    - [1.2.6 Install requirements](#126-install-requirements)
    - [1.2.7 Run the project](#127-run-the-project)
    - [1.2.7.1 Open CMD and navigate inside the project directory](#1271-open-cmd-and-navigate-inside-the-project-directory)
    - [1.2.8.2  Activate virtual python environment.](#1282--activate-virtual-python-environment)
    - [1.2.8.3 Copy .env.example file to .env](#1283-copy-envexample-file-to-env)
    - [1.2.8.4 Run the following commands to setup the database](#1284-run-the-following-commands-to-setup-the-database)
    - [1.2.10 Start the server(Finally)](#1210-start-the-serverfinally)
  - [1.3 Linux](#13-linux)
    - [1.3.1 Install Python3](#131-install-python3)
    - [1.3.2 Install git](#132-install-git)
    - [1.3.3 Install sqlite3](#133-install-sqlite3)
    - [1.3.4 Install VSCode](#134-install-vscode)
    - [1.3.5 Clone the Project Locally](#135-clone-the-project-locally)
    - [1.3.6 Install and Create Virtual Environment](#136-install-and-create-virtual-environment)
    - [1.3.7 Install requirements](#137-install-requirements)
    - [1.3.8 Run the project](#138-run-the-project)
    - [1.3.8.1 Open terminal and navigate inside the project directory](#1381-open-terminal-and-navigate-inside-the-project-directory)
    - [1.3.8.2  Activate virtual python environment.](#1382--activate-virtual-python-environment)
    - [1.3.8.3 Copy .env.example file to .env](#1383-copy-envexample-file-to-env)
    - [1.3.8.4 Run the following commands to setup the database](#1384-run-the-following-commands-to-setup-the-database)
    - [1.3.10 Start the server(Finally)](#1310-start-the-serverfinally)
- [Working on a new features](#working-on-a-new-features)
- [Troubleshooting[WIP]](#troubleshootingwip)
  - [MAC](#mac)
    - [Homebrew not found](#homebrew-not-found)
  - [Windows](#windows)
  - [Linux](#linux)





# 1. Setting up your system for the first time


## 1.1 MacOS

### 1.1.1 Install HomeBrew

Homebrew is a free and open-source software package management system that simplifies the installation of software on Apple's operating system, macOS, as well as Linux [source](https://en.wikipedia.org/wiki/Homebrew_(package_manager)).

We will use homebrew to install python on our MAC, to use homebrew for python installation, we need to first install a compiler which we can get by  installing Xcode's command-line tools.

To install the xcode, open terminal on your system, and enter the following command

```sh
xcode-select --install
```

Now that you have the Xcode's command-line tools installed, lets go ahead and install homebrew

To install [homebrew](https://brew.sh/), paste the following command on your terminal. 

```sh
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```
*Note*: Homebrew might need you to use one more command to add homebrew to your `PATH`, please carefully check if the home brew has *NEXT STEPS* for you on terminal after the installation


### 1.1.2 Install Python

Now that we have home brew installed, Lets go ahea and install [python3](https://docs.python-guide.org/starting/install3/osx/)


```sh
brew update
brew install python
```
To confirm that you have python3 installed and can be accessed, please check this guide from [Official python installation for mac](https://docs.python-guide.org/starting/install3/osx/#working-with-python-3)

In summary, you should be able to access python3 with the command `python`, you can quickly check the python version by entering the command below on  the terminal

```sh
python3 --version
```

### 1.1.3 Install git

Git is free and open source software for distributed version control. We will use it later to clone the Physio-net project to our system, and you can also use it to submit your contribution to the project. 
Here are few resources to learn about git [git-scm.com](https://git-scm.com/book/en/v2/Getting-Started-What-is-Git%3F), [w3schools](https://www.w3schools.com/git/)

```sh
brew install git
```

To verify git is installed correctly, you can run the following in terminal

```sh
git --version
```

### 1.1.4 Install sqlite3

The physionet-build uses sqlite3 as a quick database for local setup. Lets install that

```sh
brew install sqlite3
```
### 1.1.5 Install VSCode

To setup, VSCode, you can download it from [official link](https://code.visualstudio.com/) and install directly on your MAC

After installing VSCode, you can install this [Python extension on VSCode](https://marketplace.visualstudio.com/items?itemName=ms-python.python) to get the support for IntelliSense (Pylance), Linting, Debugging (multi-threaded, remote), Jupyter Notebooks, code formatting, refactoring, unit tests, and more. 
Simply vist the link above and click on the install button on the website, it should redirect and open the installation option on VSCode.

### 1.1.6 Clone the Project Locally

Now that we have Python setup, Lets go ahead and clone the project to your system. Open terminal and enter the following command.


```sh
git clone https://github.com/MIT-LCP/physionet-build
```

### 1.1.7 Install and Create Virtual Environment

Now that we have cloned the project to your system, lets go ahead and create a Virtual Environment, you can learn more about Virtual Environments in python [Here](https://realpython.com/python-virtual-environments-a-primer/). 

In Summary, Virtual Environment will let us install and keep different versions of python library specific to individual projects.

Lets create a virtual environment for our project

1.1.7.1 Create a Virtual Environment

Open terminal and enter the following command to navigate inside the project directory

```sh
cd physionet-build
```
Now create the virtual environment with the following command in the same terminal
```sh
python3 -m venv env
```

1.1.7.2 Activate the Virtual Environment

In the same terminal from  step 1.1.7.1, enter the following command to activate the virtual environment

```sh
source env/bin/activate
```


### 1.1.8 Install requirements

Now that we have the Virtual Environment setup, lets install the python libraries needed for the project.

In the same terminal from step 1.1.7.2, enter the following command to install the requirements

```sh
pip install -r requirements.txt
```

### 1.1.9 Run the project
We now have everything setup to run the project locally. Lets go ahead and setup the project

### 1.1.9.1 Open terminal and navigate inside the project directory

```sh
cd physionet-build
```



### 1.1.9.2  Activate virtual python environment.

```sh
source env/bin/activate
```

### 1.1.9.3 Copy .env.example file to .env

```sh
cp .env.example .env
```



### 1.1.9.4 Run the following commands to setup the database

  - Run: `python3 manage.py resetdb` to reset the database with the latest applied migrations.

  - Run: `python3 manage.py loaddemo` to load the demo fixtures set up example files.
  
  - Run: `python3 manage.py compilestatic` to compile the css files

### 1.1.10 Start the server(Finally)

Enter the following command to start the server

```sh
python3 manage.py runserver
```

The local development server will be available at [http://localhost:8000](http://localhost:8000).




## 1.2 Windows


### 1.2.1 Install Python3

*Note: Check if you alredy have a python3 installed on your system(if you already have a latest version of python3, you wont to do do the step 1.2.1), to check enter the following on CMD*

```sh
python --version
```

If you dont have a latest version of python, Please download and install latest python from the [Official Python Website](https://www.python.org/downloads/). 

1. Navigate to the Downloads tab for Windows.
2. Choose the latest Python 3 release
3. Choose the Windows x86 executable installer if you are using a 32-bit installer or if you have a 64-bit system, then download Windows x86-64 executable installer. 
4. Run the executable and install python with the default options
   1. Dont forget to select the `Add Python x.x to PATH` option
   
   Here is a detailed [guide](https://realpython.com/installing-python/#how-to-install-python-on-windows) if you need further help

Open cmd and enter the following commands to verify you have installed python3


```sh
python --version
```

### 1.2.2 Install git Bash
Download git bash from the official website and install it with the default settings

https://git-scm.com/download/win

Git is free and open source software for distributed version control. We will use it later to clone the Physio-net project to our system, and you can also use it to submit your contribution to the project. 
Here are few resources to learn about git [git-scm.com](https://git-scm.com/book/en/v2/Getting-Started-What-is-Git%3F), [w3schools](https://www.w3schools.com/git/)



### 1.2.3 Install VSCode

To setup, VSCode, you can download the .exe package from [official link](https://code.visualstudio.com/) and install directly on your Windows. [Here](https://code.visualstudio.com/docs/setup/windows) are the official instructions 


After installing VSCode, you can install this [Python extension on VSCode](https://marketplace.visualstudio.com/items?itemName=ms-python.python) to get the support for IntelliSense (Pylance), Linting, Debugging (multi-threaded, remote), Jupyter Notebooks, code formatting, refactoring, unit tests, and more. 
Simply vist the link above and click on the install button on the website, it should redirect and open the installation option on VSCode.

### 1.2.4 Clone the Project Locally

Now that we have Python setup, Lets go ahead and clone the project to your system. Open git bash and enter the following command.


```sh
git clone https://github.com/MIT-LCP/physionet-build
```

### 1.2.5 Install and Create Virtual Environment

Now that we have cloned the project to your system, lets go ahead and create a Virtual Environment, you can learn more about Virtual Environments in python [Here](https://realpython.com/python-virtual-environments-a-primer/). 

In Summary, Virtual Environment will let us install and keep different versions of python library specific to individual projects.

Lets create a virtual environment for our project

1.2.5.1 Create a Virtual Environment

Open CMD and  navigate inside the project directory

```sh
cd <path to physionet-build>
```
Now create the virtual environment with the following command in the same terminal
```sh
python3 -m venv env
```

1.2.5.2 Activate the Virtual Environment

In the same CMD from  step 1.2.5.1, enter the following command to activate the virtual environment

```sh
env\Scripts\activate.bat
```

### 1.2.6 Install requirements

Now that we have the Virtual Environment setup, lets install the python libraries needed for the project.

In the same terminal from step 1.2.5.2, enter the following command to install the requirements

```sh
pip install -r requirements.txt
```

### 1.2.7 Run the project

We now have everything setup to run the project locally. Lets go ahead and setup the project

### 1.2.7.1 Open CMD and navigate inside the project directory

```sh
cd <path to physionet-build>
```

### 1.2.8.2  Activate virtual python environment.

```sh
env\Scripts\activate.bat
```

### 1.2.8.3 Copy .env.example file to .env

```sh
copy .env.example .env
```


### 1.2.8.4 Run the following commands to setup the database

  - Run: `python3 manage.py resetdb` to reset the database with the latest applied migrations.

  - Run: `python3 manage.py loaddemo` to load the demo fixtures set up example files.

  - Run: `python3 manage.py compilestatic` to compile the css files


### 1.2.10 Start the server(Finally)

Enter the following command to start the server

```sh
python3 manage.py runserver
```

The local development server will be available at [http://localhost:8000](http://localhost:8000).



## 1.3 Linux


### 1.3.1 Install Python3

Because has many linux distros, please follow the guide from [realpython](https://realpython.com/installing-python/#how-to-install-python-on-linux) to setup python3 based on your linux system

Here we have added instruction on installing python3 on Ubuntu(Debian based Linux Distro).

Open terminal and enter the following commands

```sh
sudo apt update
sudo apt install software-properties-common
```

```sh
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3
```


To confirm that you have python3 installed and can be accessed, please check this guide for [Python installation for Linux](https://docs.python-guide.org/starting/install3/linux/#working-with-python-3)

In summary, you should be able to access python3 with the command `python3`, you can quickly check the python version by entering the command below on  the terminal

```sh
python3 --version
```

### 1.3.2 Install git

Git is free and open source software for distributed version control. We will use it later to clone the Physio-net project to our system, and you can also use it to submit your contribution to the project. 
Here are few resources to learn about git [git-scm.com](https://git-scm.com/book/en/v2/Getting-Started-What-is-Git%3F), [w3schools](https://www.w3schools.com/git/)

```sh
sudo apt install git
```

To verify git is installed correctly, you can run the following in terminal

```sh
git --version
```

### 1.3.3 Install sqlite3

The physionet-build uses sqlite3 as a quick database for local setup. Lets install that

```sh
sudo apt install sqlite3
```

### 1.3.4 Install VSCode

To setup, VSCode, you can download the .deb package from [official link](https://code.visualstudio.com/) and install directly on your Linux with the following the instructions [here](https://code.visualstudio.com/docs/setup/linux)


```sh
sudo apt install ./<path to your downloaded vscode file>.deb
```

After installing VSCode, you can install this [Python extension on VSCode](https://marketplace.visualstudio.com/items?itemName=ms-python.python) to get the support for IntelliSense (Pylance), Linting, Debugging (multi-threaded, remote), Jupyter Notebooks, code formatting, refactoring, unit tests, and more. 
Simply vist the link above and click on the install button on the website, it should redirect and open the installation option on VSCode.

### 1.3.5 Clone the Project Locally

Now that we have Python setup, Lets go ahead and clone the project to your system. Open terminal and enter the following command.


```sh
git clone https://github.com/MIT-LCP/physionet-build
```

### 1.3.6 Install and Create Virtual Environment

Now that we have cloned the project to your system, lets go ahead and create a Virtual Environment, you can learn more about Virtual Environments in python [Here](https://realpython.com/python-virtual-environments-a-primer/). 

In Summary, Virtual Environment will let us install and keep different versions of python library specific to individual projects.

Lets create a virtual environment for our project

1.3.6.1 Create a Virtual Environment

Open terminal and enter the following command to navigate inside the project directory

```sh
cd physionet-build
```
Now create the virtual environment with the following command in the same terminal
```sh
python3 -m venv env
```

1.3.6.2 Activate the Virtual Environment

In the same terminal from  step 1.3.6.1, enter the following command to activate the virtual environment

```sh
source env/bin/activate
```


### 1.3.7 Install requirements

Now that we have the Virtual Environment setup, lets install the python libraries needed for the project.

In the same terminal from step 1.3.6.2, enter the following command to install the requirements

```sh
pip install -r requirements.txt
```

### 1.3.8 Run the project

We now have everything setup to run the project locally. Lets go ahead and setup the project

### 1.3.8.1 Open terminal and navigate inside the project directory

```sh
cd physionet-build
```



### 1.3.8.2  Activate virtual python environment.

```sh
source env/bin/activate
```

### 1.3.8.3 Copy .env.example file to .env

```sh
cp .env.example .env
```


### 1.3.8.4 Run the following commands to setup the database

  - Run: `python3 manage.py resetdb` to reset the database with the latest applied migrations.

  - Run: `python3 manage.py loaddemo` to load the demo fixtures set up example files.

  - Run: `python3 manage.py compilestatic` to compile the css files


### 1.3.10 Start the server(Finally)

Enter the following command to start the server

```sh
python3 manage.py runserver
```

The local development server will be available at [http://localhost:8000](http://localhost:8000).



# Working on a new features

Now that you have completed your setup and have familiarized yourself with the codebase, here is how you can contribute and submit your changes for review.

1. Create a new Branch each feature you work on
2. Work on your changes, add files and commit your changes
3. On Commits, add clear explanation on the changes. Here is an interesting read from [freeCodeCamp](https://www.freecodecamp.org/news/how-to-write-better-git-commit-messages/)
4. Once your changes are final and ready to be submitted, push the changes and open a Merge Request. Someone will review your changes ASAP.




Here are some good resources to read about contributing to OpenSource projects
1. [Making your first Open Source Pull Request | Github](https://www.geeksforgeeks.org/making-first-open-source-pull-request/)
2. [A First Timers Guide to an Open Source Project](https://auth0.com/blog/a-first-timers-guide-to-an-open-source-project/)
3. [Contributing to Open Source : Getting Started](https://www.geeksforgeeks.org/contributing-to-open-source-getting-started)
4. [The (written) unwritten guide to pull requests
](https://www.atlassian.com/blog/git/written-unwritten-guide-pull-requests)



# Troubleshooting[WIP]


## MAC

### Homebrew not found

If you get the error `zsh: command not found: brew`, probably homebrew was saved in /opt/homebrew/ instead of /user/local/…

If that’s the case, you have to modify your PATH with the command below (more details on [StackOverflow](https://stackoverflow.com/questions/36657321/after-installing-homebrew-i-get-zsh-command-not-found-brew)).

`export PATH=/opt/homebrew/bin:$PATH`


## Windows


## Linux